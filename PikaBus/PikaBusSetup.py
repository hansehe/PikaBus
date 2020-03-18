import pika
from pika import frame, exceptions
import asyncio
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor
import functools
import retry
from PikaBus.abstractions.AbstractPikaBusSetup import AbstractPikaBusSetup
from PikaBus.abstractions.AbstractPikaSerializer import AbstractPikaSerializer
from PikaBus.abstractions.AbstractPikaProperties import AbstractPikaProperties
from PikaBus.abstractions.AbstractPikaErrorHandler import AbstractPikaErrorHandler
from PikaBus.abstractions.AbstractPikaMessageHandler import AbstractPikaMessageHandler
from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus
from PikaBus import PikaSerializer, PikaProperties, PikaErrorHandler, PikaBus
from PikaBus.tools import PikaSteps, PikaConstants, PikaTools


class PikaBusSetup(AbstractPikaBusSetup):
    def __init__(self, connParams: pika.ConnectionParameters,
                 defaultListenerQueue: str = None,
                 directExchange: str = 'PikaBusDirect',
                 topicExchange: str = 'PikaBusTopic',
                 pikaSerializer: AbstractPikaSerializer = None,
                 pikaProperties: AbstractPikaProperties = None,
                 pikaErrorHandler: AbstractPikaErrorHandler = None,
                 pikaBusCreateMethod=None,
                 retryParams: dict = None,
                 logger=logging.getLogger(__name__)):
        """
        :param pika.ConnectionParameters connParams: Pika connection parameters.
        :param str defaultListenerQueue: Pika default listener queue to receive messages. Set to None to act purely as a publisher.
        :param str directExchange: Command exchange to publish direct command messages. The command pattern is used to directly sending a message to one consumer.
        :param str topicExchange: Event exchange to publish event messages. The event pattern is used to publish a message to any listening consumers.
        :param AbstractPikaSerializer pikaSerializer: Optional serializer override.
        :param AbstractPikaProperties pikaProperties: Optional properties override.
        :param AbstractPikaErrorHandler pikaErrorHandler: Optional error handler override.
        :param def pikaBusCreateMethod: Optional pikaBus creator method which returns an instance of AbstractPikaBus.
        :param dict retryParams: A set of retry parameters. See options below in code.
        :param logging logger: Logging object
        """
        if pikaSerializer is None:
            pikaSerializer = PikaSerializer.PikaSerializer()
        if pikaProperties is None:
            pikaProperties = PikaProperties.PikaProperties()
        if pikaErrorHandler is None:
            pikaErrorHandler = PikaErrorHandler.PikaErrorHandler()
        if pikaBusCreateMethod is None:
            pikaBusCreateMethod = self._DefaultPikaBusCreator
        if retryParams is None:
            retryParams = {'tries': -1, 'delay': 1, 'max_delay': 10, 'backoff': 1, 'jitter': 1}

        self._connParams = connParams
        self._defaultListenerQueue = defaultListenerQueue
        self._directExchange = directExchange
        self._topicExchange = topicExchange
        self._pikaSerializer = pikaSerializer
        self._pikaProperties = pikaProperties
        self._pikaErrorHandler = pikaErrorHandler
        self._pipeline = self._BuildPikaPipeline()
        self._messageHandlers = []
        self._openChannels = {}
        self._forceCloseChannelIds = {}
        self._openConnections = {}
        self._pikaBusCreateMethod = pikaBusCreateMethod
        self._retryParams = retryParams
        self._logger = logger

    def __del__(self):
        self.Stop()

    @property
    def pipeline(self):
        return self._pipeline

    @property
    def channels(self):
        return dict(self._openChannels)

    @property
    def messageHandlers(self):
        return self._messageHandlers

    def Start(self, listenerQueue: str = None):
        listenerQueue = self._AssertListenerQueueIsSet(listenerQueue)
        with pika.BlockingConnection(self._connParams) as connection:
            channelId = str(uuid.uuid1())
            onMessageCallback = functools.partial(self._OnMessageCallBack,
                                                  connection=connection,
                                                  channelId=channelId,
                                                  listenerQueue=listenerQueue)
            channel: pika.adapters.blocking_connection.BlockingChannel = connection.channel()
            PikaTools.CreateDurableQueue(channel, listenerQueue)
            channel.basic_consume(listenerQueue, onMessageCallback)
            self._openChannels[channelId] = channel
            self._openConnections[channelId] = connection
            self._logger.info(f'Starting new consumer channel with id {channelId} '
                              f'and {len(self.channels)} ongoing channels.')
            try:
                channel.start_consuming()
            # Don't recover connections closed by client or underlying bugs.
            except (pika.exceptions.ConnectionClosedByClient, AttributeError) as exception:
                self._logger.warning(f'{str(type(exception))}: {str(exception)}')
            except Exception as exception:
                self._logger.exception(f'{str(type(exception))}: {str(exception)}')
                if channelId not in self._forceCloseChannelIds:
                    self._logger.debug(f'Consumer with channel id {channelId} '
                                       f'failed due to unknown exception - '
                                       f'{str(type(exception))}: {str(exception)}')
                    raise
            finally:
                self._openChannels.pop(channelId)
                self._openConnections.pop(channelId)
                if channelId in self._forceCloseChannelIds:
                    self._forceCloseChannelIds.pop(channelId)
        self._logger.info(f'Closing consumer channel with id {channelId}.')

    def Stop(self, channelId: str = None):
        openChannels = self.channels
        openConnections = dict(self._openConnections)
        if channelId is None:
            for openChannelId in openChannels:
                self.Stop(openChannelId)
        else:
            channel: pika.adapters.blocking_connection.BlockingChannel = openChannels[channelId]
            if channel.is_open:
                self._forceCloseChannelIds[channelId] = channel
                try:
                    channel.stop_consuming()
                except Exception as exception:
                    self._logger.warning(str(exception))
                    connection: pika.BlockingConnection = openConnections[channelId]
                    PikaTools.SafeCloseConnection(connection)

    def StartAsync(self,
                   consumers: int = 1,
                   listenerQueue: str = None,
                   loop: asyncio.AbstractEventLoop = None,
                   executor: ThreadPoolExecutor = None):
        listenerQueue = self._AssertListenerQueueIsSet(listenerQueue)
        self._AssertConnection(listenerQueue=listenerQueue,
                               createListenerQueueOnConnected=True)
        if loop is None:
            loop = asyncio.get_event_loop()
        tasks = []
        for i in range(consumers):
            func = functools.partial(self._StartConsumerWithRetryHandler,
                                     listenerQueue=listenerQueue)
            task = loop.run_in_executor(executor, func)
            futureTask = asyncio.ensure_future(task, loop=loop)
            tasks.append(futureTask)
        return tasks

    def CreateBus(self, listenerQueue: str = None):
        connection = pika.BlockingConnection(self._connParams)
        channel = connection.channel()
        listenerQueue = self._GetListenerQueue(listenerQueue)
        data = self._CreateDefaultDataHolder(connection, channel, listenerQueue)
        pikaBus: AbstractPikaBus = self._pikaBusCreateMethod(data=data, closeConnectionOnDelete=True)
        return pikaBus

    def AddMessageHandler(self, messageHandler: AbstractPikaMessageHandler):
        self._messageHandlers.append(messageHandler)

    def _StartConsumerWithRetryHandler(self, listenerQueue: str):
        retryException = pika.exceptions.AMQPConnectionError
        tries = self._retryParams.get('tries', -1)
        while tries:
            retry.api.retry_call(self._AssertConnection,
                                 exceptions=retryException,
                                 tries=tries,
                                 delay=self._retryParams.get('delay', 1),
                                 max_delay=self._retryParams.get('max_delay', 10),
                                 backoff=self._retryParams.get('backoff', 1),
                                 jitter=self._retryParams.get('jitter', 1),
                                 logger=self._logger)
            try:
                return self.Start(listenerQueue)
            except retryException as exception:
                self._logger.exception(f'{str(type(exception))}: {str(exception)}')
            tries -= 1

    def _AssertConnection(self, listenerQueue: str = None, createListenerQueueOnConnected = False):
        with pika.BlockingConnection(self._connParams) as connection:
            channel: pika.adapters.blocking_connection.BlockingChannel = connection.channel()
            if createListenerQueueOnConnected:
                PikaTools.CreateDurableQueue(channel, listenerQueue)

    def _BuildPikaPipeline(self):
        pipeline = [
            PikaSteps.TryHandleMessageInPipeline,
            PikaSteps.CheckIfMessageIsDeferred,
            PikaSteps.SerializeMessage,
            PikaSteps.HandleMessage,
            PikaSteps.AcknowledgeMessage,
        ]
        return pipeline

    def _OnMessageCallBack(self,
                           channel: pika.adapters.blocking_connection.BlockingChannel,
                           methodFrame: frame.Method,
                           headerFrame: frame.Header,
                           body: bytes,
                           connection: pika.BlockingConnection,
                           channelId: str,
                           listenerQueue: str):
        self._logger.debug(f"Received new message on channel {channelId}")
        data = self._CreateDefaultDataHolder(connection, channel, listenerQueue)
        data[PikaConstants.DATA_KEY_MESSAGE_HANDLERS] = list(self.messageHandlers)
        incomingMessage = {
            PikaConstants.DATA_KEY_METHOD_FRAME: methodFrame,
            PikaConstants.DATA_KEY_HEADER_FRAME: headerFrame,
            PikaConstants.DATA_KEY_BODY: body,
        }
        data[PikaConstants.DATA_KEY_INCOMING_MESSAGE] = incomingMessage

        pikaBus: AbstractPikaBus = self._pikaBusCreateMethod(data=data, closeConnectionOnDelete=False)
        data[PikaConstants.DATA_KEY_BUS] = pikaBus

        pipelineIterator = iter(self._pipeline)
        PikaSteps.HandleNextStep(pipelineIterator, data)
        self._logger.debug(f"Successfully handled message on channel {channelId}")

    def _CreateDefaultDataHolder(self,
                                 connection: pika.BlockingConnection,
                                 channel: pika.adapters.blocking_connection.BlockingChannel,
                                 listenerQueue: str):
        data = {
            PikaConstants.DATA_KEY_LISTENING_QUEUE: listenerQueue,
            PikaConstants.DATA_KEY_DIRECT_EXCHANGE: self._directExchange,
            PikaConstants.DATA_KEY_TOPIC_EXCHANGE: self._topicExchange,
            PikaConstants.DATA_KEY_CONNECTION: connection,
            PikaConstants.DATA_KEY_CHANNEL: channel,
            PikaConstants.DATA_KEY_SERIALIZER: self._pikaSerializer,
            PikaConstants.DATA_KEY_PROPERTY_BUILDER: self._pikaProperties,
            PikaConstants.DATA_KEY_ERROR_HANDLER: self._pikaErrorHandler,
            PikaConstants.DATA_KEY_LOGGER: self._logger,
            PikaConstants.DATA_KEY_OUTGOING_MESSAGES: []
        }
        return data

    def _GetListenerQueue(self, listenerQueue: str = None):
        if listenerQueue is None:
            listenerQueue = self._defaultListenerQueue
        return listenerQueue

    def _AssertListenerQueueIsSet(self, listenerQueue: str):
        listenerQueue = self._GetListenerQueue(listenerQueue)
        if listenerQueue is None:
            msg = "Listening queue is not set, so you cannot start the listener process."
            self._logger.exception(msg)
            raise Exception(msg)
        return listenerQueue

    def _DefaultPikaBusCreator(self, data: dict, closeConnectionOnDelete: bool = False):
        return PikaBus.PikaBus(data=data, closeConnectionOnDelete=closeConnectionOnDelete)
