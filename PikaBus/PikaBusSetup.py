import pika
from pika import frame, exceptions
import asyncio
import uuid
import logging
from typing import Union, Callable, List
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
                 defaultSubscriptions: Union[List[str], str] = None,
                 defaultDirectExchange: str = 'PikaBusDirect',
                 defaultTopicExchange: str = 'PikaBusTopic',
                 defaultListenerQueueSettings: dict = None,
                 defaultDirectExchangeSettings: dict = None,
                 defaultTopicExchangeSettings: dict = None,
                 pikaSerializer: AbstractPikaSerializer = None,
                 pikaProperties: AbstractPikaProperties = None,
                 pikaErrorHandler: AbstractPikaErrorHandler = None,
                 pikaBusCreateMethod: Callable = None,
                 retryParams: dict = None,
                 confirmDelivery: bool = True,
                 logger=logging.getLogger(__name__)):
        """
        :param pika.ConnectionParameters connParams: Pika connection parameters.
        :param str defaultListenerQueue: Pika default listener queue to receive messages. Set to None to act purely as a publisher.
        :param [str] | str defaultSubscriptions: Default topic or a list of topics to subscribe.
        :param str defaultDirectExchange: Default command exchange to publish direct command messages. The command pattern is used to directly sending a message to one consumer.
        :param str defaultTopicExchange: Default event exchange to publish event messages. The event pattern is used to publish a message to any listening consumers.
        :param dict defaultListenerQueueSettings: Default listener queue settings. 'arguments': {`ha-mode: all`} is activated by default to mirror the queue across all nodes.
        :param dict defaultDirectExchangeSettings: Default direct exchange settings.
        :param dict defaultTopicExchangeSettings: Default topic exchange settings.
        :param AbstractPikaSerializer pikaSerializer: Optional serializer override.
        :param AbstractPikaProperties pikaProperties: Optional properties override.
        :param AbstractPikaErrorHandler pikaErrorHandler: Optional error handler override.
        :param def pikaBusCreateMethod: Optional pikaBus creator method which returns an instance of AbstractPikaBus.
        :param dict retryParams: A set of retry parameters. See options below in code.
        :param bool confirmDelivery: Activate confirm delivery with publisher confirms on all channels.
        :param logging logger: Logging object
        """
        if defaultSubscriptions is None:
            defaultSubscriptions = []
        if defaultListenerQueueSettings is None:
            defaultListenerQueueSettings = {'arguments': {'ha-mode': 'all'}}
        if defaultDirectExchangeSettings is None:
            defaultDirectExchangeSettings = {'exchange_type': 'direct'}
        if defaultTopicExchangeSettings is None:
            defaultTopicExchangeSettings = {'exchange_type': 'topic'}
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
        self._defaultSubscriptions = defaultSubscriptions
        self._defaultDirectExchange = defaultDirectExchange
        self._defaultTopicExchange = defaultTopicExchange
        self._defaultListenerQueueSettings = defaultListenerQueueSettings
        self._defaultDirectExchangeSettings = defaultDirectExchangeSettings
        self._defaultTopicExchangeSettings = defaultTopicExchangeSettings
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
        self._confirmDelivery = confirmDelivery
        self._logger = logger

    def __del__(self):
        self.Stop()

    @property
    def pipeline(self):
        return self._pipeline

    @property
    def connections(self):
        return dict(self._openConnections)

    @property
    def channels(self):
        return dict(self._openChannels)

    @property
    def messageHandlers(self):
        return self._messageHandlers

    def Init(self,
             listenerQueue: str = None,
             listenerQueueSettings: dict = None,
             topicExchange: str = None,
             topicExchangeSettings: dict = None,
             directExchange: str = None,
             directExchangeSettings: dict = None,
             subscriptions: Union[List[str], str] = None):
        listenerQueue, listenerQueueSettings = self._GetListenerQueue(listenerQueue, listenerQueueSettings)
        self._AssertConnection(createDefaultRabbitMqSetup=True,
                               listenerQueue=listenerQueue,
                               listenerQueueSettings=listenerQueueSettings,
                               topicExchange=topicExchange,
                               topicExchangeSettings=topicExchangeSettings,
                               directExchange=directExchange,
                               directExchangeSettings=directExchangeSettings,
                               subscriptions=subscriptions)

    def Start(self,
              listenerQueue: str = None,
              listenerQueueSettings: dict = None,
              topicExchange: str = None,
              topicExchangeSettings: dict = None,
              directExchange: str = None,
              directExchangeSettings: dict = None,
              subscriptions: Union[List[str], str] = None):
        listenerQueue, listenerQueueSettings = self._AssertListenerQueueIsSet(listenerQueue, listenerQueueSettings)
        with pika.BlockingConnection(self._connParams) as connection:
            channelId = str(uuid.uuid1())
            onMessageCallback = functools.partial(self._OnMessageCallBack,
                                                  connection=connection,
                                                  channelId=channelId,
                                                  listenerQueue=listenerQueue,
                                                  topicExchange=topicExchange,
                                                  directExchange=directExchange)
            channel: pika.adapters.blocking_connection.BlockingChannel = connection.channel()
            self._CreateDefaultRabbitMqSetup(channel,
                                             listenerQueue,
                                             listenerQueueSettings,
                                             topicExchange,
                                             topicExchangeSettings,
                                             directExchange,
                                             directExchangeSettings,
                                             subscriptions)
            channel.basic_consume(listenerQueue, onMessageCallback)
            self._openChannels[channelId] = channel
            self._openConnections[channelId] = connection
            self._logger.info(f'Starting new consumer channel with id {channelId} '
                              f'and {len(self.channels)} ongoing channels.')
            try:
                channel.start_consuming()
            # Don't recover connections closed by client or underlying bugs.
            except (pika.exceptions.ConnectionClosedByClient, AttributeError) as exception:
                self._logger.exception(f'Ignoring - {str(type(exception))}: {str(exception)}')
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

    def Stop(self,
             channelId: str = None):
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
                    self._logger.exception(f'Ignoring - {str(exception)}')
                    connection: pika.BlockingConnection = openConnections[channelId]
                    PikaTools.SafeCloseConnection(connection)

    def StartAsync(self,
                   consumers: int = 1,
                   listenerQueue: str = None,
                   listenerQueueSettings: dict = None,
                   topicExchange: str = None,
                   topicExchangeSettings: dict = None,
                   directExchange: str = None,
                   directExchangeSettings: dict = None,
                   subscriptions: Union[List[str], str] = None,
                   loop: asyncio.AbstractEventLoop = None,
                   executor: ThreadPoolExecutor = None):
        listenerQueue, listenerQueueSettings = self._AssertListenerQueueIsSet(listenerQueue, listenerQueueSettings)
        self._AssertConnection(createDefaultRabbitMqSetup=True,
                               listenerQueue=listenerQueue,
                               listenerQueueSettings=listenerQueueSettings,
                               topicExchange=topicExchange,
                               topicExchangeSettings=topicExchangeSettings,
                               directExchange=directExchange,
                               directExchangeSettings=directExchangeSettings,
                               subscriptions=subscriptions)
        if loop is None:
            loop = asyncio.get_event_loop()
        tasks = []
        for i in range(consumers):
            func = functools.partial(self._StartConsumerWithRetryHandler,
                                     listenerQueue=listenerQueue,
                                     listenerQueueSettings=listenerQueueSettings,
                                     topicExchange=topicExchange,
                                     topicExchangeSettings=topicExchangeSettings,
                                     directExchange=directExchange,
                                     directExchangeSettings=directExchangeSettings,
                                     subscriptions=subscriptions)
            task = loop.run_in_executor(executor, func)
            futureTask = asyncio.ensure_future(task, loop=loop)
            tasks.append(futureTask)
        return tasks

    def CreateBus(self,
                  listenerQueue: str = None,
                  topicExchange: str = None,
                  directExchange: str = None,
                  connection: pika.adapters.blocking_connection = None):

        closeConnectionOnDelete = False
        if connection is None:
            closeConnectionOnDelete = True
            connection = pika.BlockingConnection(self._connParams)

        channel = connection.channel()
        if self._confirmDelivery:
            channel.confirm_delivery()

        listenerQueue, listenerQueueSettings = self._GetListenerQueue(listenerQueue)
        data = self._CreateDefaultDataHolder(connection, channel, listenerQueue,
                                             topicExchange=topicExchange,
                                             directExchange=directExchange)
        pikaBus: AbstractPikaBus = self._pikaBusCreateMethod(data=data,
                                                             closeChannelOnDelete=True,
                                                             closeConnectionOnDelete=closeConnectionOnDelete)
        return pikaBus

    def AddMessageHandler(self, messageHandler: Union[AbstractPikaMessageHandler, Callable]):
        self._messageHandlers.append(messageHandler)

    def _StartConsumerWithRetryHandler(self,
                                       listenerQueue: str,
                                       listenerQueueSettings: dict,
                                       topicExchange: str,
                                       topicExchangeSettings: dict,
                                       directExchange: str,
                                       directExchangeSettings: dict,
                                       subscriptions: Union[List[str], str]):
        tries = self._retryParams.get('tries', -1)
        while tries:
            retry.api.retry_call(self._AssertConnection,
                                 exceptions=Exception,
                                 tries=tries,
                                 delay=self._retryParams.get('delay', 1),
                                 max_delay=self._retryParams.get('max_delay', 10),
                                 backoff=self._retryParams.get('backoff', 1),
                                 jitter=self._retryParams.get('jitter', 1),
                                 logger=self._logger)
            try:
                self.Start(
                    listenerQueue=listenerQueue,
                    listenerQueueSettings=listenerQueueSettings,
                    topicExchange=topicExchange,
                    topicExchangeSettings=topicExchangeSettings,
                    directExchange=directExchange,
                    directExchangeSettings=directExchangeSettings,
                    subscriptions=subscriptions)
                return
            except Exception as exception:
                self._logger.exception(f'{str(type(exception))}: {str(exception)}')
            tries -= 1

    def _AssertConnection(self,
                          createDefaultRabbitMqSetup = False,
                          listenerQueue: str = None,
                          listenerQueueSettings: dict = None,
                          topicExchange: str = None,
                          topicExchangeSettings: dict = None,
                          directExchange: str = None,
                          directExchangeSettings: dict = None,
                          subscriptions: Union[List[str], str] = None):
        with pika.BlockingConnection(self._connParams) as connection:
            channel: pika.adapters.blocking_connection.BlockingChannel = connection.channel()
            if createDefaultRabbitMqSetup:
                self._CreateDefaultRabbitMqSetup(channel,
                                                 listenerQueue,
                                                 listenerQueueSettings,
                                                 topicExchange,
                                                 topicExchangeSettings,
                                                 directExchange,
                                                 directExchangeSettings,
                                                 subscriptions)

    def _CreateDefaultRabbitMqSetup(self,
                                    channel: pika.adapters.blocking_connection.BlockingChannel,
                                    listenerQueue: str,
                                    listenerQueueSettings: dict,
                                    topicExchange: str = None,
                                    topicExchangeSettings: dict = None,
                                    directExchange: str = None,
                                    directExchangeSettings: dict = None,
                                    subscriptions: Union[List[str], str] = None):
        if self._confirmDelivery:
            channel.confirm_delivery()
        if topicExchange is None:
            topicExchange = self._defaultTopicExchange
        if topicExchangeSettings is None:
            topicExchangeSettings = self._defaultTopicExchangeSettings
        if directExchange is None:
            directExchange = self._defaultDirectExchange
        if directExchangeSettings is None:
            directExchangeSettings = self._defaultDirectExchangeSettings
        if subscriptions is None:
            subscriptions = self._defaultSubscriptions
        PikaTools.CreateExchange(channel, directExchange, settings=directExchangeSettings)
        PikaTools.CreateExchange(channel, topicExchange, settings=topicExchangeSettings)
        if listenerQueue is not None:
            PikaTools.CreateDurableQueue(channel, listenerQueue, settings=listenerQueueSettings)
            PikaTools.BasicSubscribe(channel, topicExchange, subscriptions, listenerQueue)

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
                           listenerQueue: str,
                           topicExchange: str = None,
                           directExchange: str = None):
        self._logger.debug(f"Received new message on channel {channelId}")
        data = self._CreateDefaultDataHolder(connection, channel, listenerQueue,
                                             topicExchange=topicExchange,
                                             directExchange=directExchange)
        data[PikaConstants.DATA_KEY_MESSAGE_HANDLERS] = list(self.messageHandlers)
        incomingMessage = {
            PikaConstants.DATA_KEY_METHOD_FRAME: methodFrame,
            PikaConstants.DATA_KEY_HEADER_FRAME: headerFrame,
            PikaConstants.DATA_KEY_BODY: body,
        }
        data[PikaConstants.DATA_KEY_INCOMING_MESSAGE] = incomingMessage

        pikaBus: AbstractPikaBus = self._pikaBusCreateMethod(data=data,
                                                             closeChannelOnDelete=False,
                                                             closeConnectionOnDelete=False)
        data[PikaConstants.DATA_KEY_BUS] = pikaBus

        pipelineIterator = iter(self._pipeline)
        PikaSteps.HandleNextStep(pipelineIterator, data)
        self._logger.debug(f"Successfully handled message on channel {channelId}")

    def _CreateDefaultDataHolder(self,
                                 connection: pika.BlockingConnection,
                                 channel: pika.adapters.blocking_connection.BlockingChannel,
                                 listenerQueue: str,
                                 topicExchange: str = None,
                                 directExchange: str = None):
        if topicExchange is None:
            topicExchange = self._defaultTopicExchange
        if directExchange is None:
            directExchange = self._defaultDirectExchange
        data = {
            PikaConstants.DATA_KEY_LISTENER_QUEUE: listenerQueue,
            PikaConstants.DATA_KEY_DIRECT_EXCHANGE: directExchange,
            PikaConstants.DATA_KEY_TOPIC_EXCHANGE: topicExchange,
            PikaConstants.DATA_KEY_CONNECTION: connection,
            PikaConstants.DATA_KEY_CHANNEL: channel,
            PikaConstants.DATA_KEY_SERIALIZER: self._pikaSerializer,
            PikaConstants.DATA_KEY_PROPERTY_BUILDER: self._pikaProperties,
            PikaConstants.DATA_KEY_ERROR_HANDLER: self._pikaErrorHandler,
            PikaConstants.DATA_KEY_LOGGER: self._logger,
            PikaConstants.DATA_KEY_OUTGOING_MESSAGES: []
        }
        return data

    def _GetListenerQueue(self,
                          listenerQueue: str = None,
                          listenerQueueSettings: dict = None):
        if listenerQueue is None:
            listenerQueue = self._defaultListenerQueue
        if listenerQueueSettings is None:
            listenerQueueSettings = self._defaultListenerQueueSettings
        return listenerQueue, listenerQueueSettings

    def _AssertListenerQueueIsSet(self, listenerQueue: str,
                                  listenerQueueSettings: dict = None):
        listenerQueue, listenerQueueSettings = self._GetListenerQueue(listenerQueue, listenerQueueSettings)
        if listenerQueue is None:
            msg = "Listening queue is not set, so you cannot start the listener process."
            self._logger.exception(msg)
            raise Exception(msg)
        return listenerQueue, listenerQueueSettings

    def _DefaultPikaBusCreator(self, data: dict,
                               closeChannelOnDelete: bool = False,
                               closeConnectionOnDelete: bool = False):
        return PikaBus.PikaBus(data=data,
                               closeChannelOnDelete=closeChannelOnDelete,
                               closeConnectionOnDelete=closeConnectionOnDelete)
