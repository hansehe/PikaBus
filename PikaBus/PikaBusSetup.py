import pika
from pika import frame, exceptions
import asyncio
import warnings
import uuid
from concurrent.futures import ThreadPoolExecutor
import functools
from retry import retry
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
                 listenerQueue: str = None,
                 directExchange: str = 'PikaBusDirect',
                 topicExchange: str = 'PikaBusTopic',
                 pikaSerializer: AbstractPikaSerializer = None,
                 pikaProperties: AbstractPikaProperties = None,
                 pikaErrorHandler: AbstractPikaErrorHandler = None):
        """
        :param pika.ConnectionParameters connParams: Pika connection parameters.
        :param str listenerQueue: Pika listening queue to received messages. Set to None to act purely as a publisher.
        :param str directExchange: Command exchange to publish direct command messages. The command pattern is used to directly sending a message to one consumer.
        :param str topicExchange: Event exchange to publish event messages. The event pattern is used to publish a message to any listening consumers.
        :param PikaBus.abstractions.AbstractPikaSerializer.AbstractPikaSerializer pikaSerializer: Optional serializer override.
        :param PikaBus.abstractions.AbstractPikaProperties.AbstractPikaProperties pikaProperties: Optional properties override.
        :param PikaBus.abstractions.AbstractPikaErrorHandler.AbstractPikaErrorHandler pikaErrorHandler: Optional error handler override.
        """
        if pikaSerializer is None:
            pikaSerializer = PikaSerializer.PikaSerializer()
        if pikaProperties is None:
            pikaProperties = PikaProperties.PikaProperties()
        if pikaErrorHandler is None:
            pikaErrorHandler = PikaErrorHandler.PikaErrorHandler()

        self._connParams = connParams
        self._listenerQueue = listenerQueue
        self._directExchange = directExchange
        self._topicExchange = topicExchange
        self._pikaSerializer = pikaSerializer
        self._pikaProperties = pikaProperties
        self._pikaErrorHandler = pikaErrorHandler
        self._pipeline = self._BuildPikaPipeline()
        self._messageHandlers = []
        self._openChannels = {}
        self._openConnections = {}

    def __del__(self):
        self.Stop()

    def pipeline(self):
        return self._pipeline

    def channels(self):
        return dict(self._openChannels)

    def messageHandlers(self):
        return self._messageHandlers

    @retry(pika.exceptions.AMQPConnectionError, delay=5, max_delay=20, jitter=1)
    def Start(self):
        self._AssertListenerQueueIsSet()
        with pika.BlockingConnection(self._connParams) as connection:
            onMessageCallback = functools.partial(
                self._OnMessageCallBack, connection=connection)
            channel: pika.adapters.blocking_connection.BlockingChannel = connection.channel()
            PikaTools.CreateDurableQueue(channel, self._listenerQueue)
            channel.basic_consume(self._listenerQueue, onMessageCallback)
            channelId = str(uuid.uuid1())
            self._openChannels[channelId] = channel
            self._openConnections[channelId] = connection
            try:
                channel.start_consuming()
            # Don't recover connections closed by server or client
            except pika.exceptions.ConnectionClosedByBroker as exception:
                warnings.warn(str(exception))
            except pika.exceptions.ConnectionClosedByClient as exception:
                warnings.warn(str(exception))
            except pika.exceptions.StreamLostError as exception:
                warnings.warn(str(exception))
            finally:
                self._openChannels.pop(channelId)
                self._openConnections.pop(channelId)

    def Stop(self, channelId: str = None):
        openChannels = self.channels()
        openConnections = dict(self._openConnections)
        if channelId is None:
            for openChannelId in openChannels:
                self.Stop(openChannelId)
        else:
            channel: pika.adapters.blocking_connection.BlockingChannel = openChannels[channelId]
            if channel.is_open:
                try:
                    channel.stop_consuming()
                except Exception as exception:
                    warnings.warn(str(exception))
                    connection: pika.BlockingConnection = openConnections[channelId]
                    PikaTools.SafeCloseConnection(connection)

    def StartAsync(self,
                   loop: asyncio.AbstractEventLoop = None,
                   executor: ThreadPoolExecutor = None):
        self._AssertListenerQueueIsSet()
        with pika.BlockingConnection(self._connParams) as connection:
            channel: pika.adapters.blocking_connection.BlockingChannel = connection.channel()
            PikaTools.CreateDurableQueue(channel, self._listenerQueue)
        if loop is None:
            loop = asyncio.get_event_loop()
        func = functools.partial(self.Start)
        task = loop.run_in_executor(executor, func)
        return asyncio.ensure_future(task, loop=loop)

    def CreateBus(self):
        connection = pika.BlockingConnection(self._connParams)
        channel = connection.channel()
        data = self._CreateDefaultDataHolder(connection, channel)
        pikaBus: AbstractPikaBus = PikaBus.PikaBus(data, closeConnectionOnDelete=True)
        return pikaBus

    def AddMessageHandler(self, messageHandler: AbstractPikaMessageHandler):
        self._messageHandlers.append(messageHandler)

    def _BuildPikaPipeline(self):
        pipeline = [
            PikaSteps.TryHandleMessageInPipeline,
            PikaSteps.SerializeMessage,
            PikaSteps.HandleMessage,
        ]
        return pipeline

    def _OnMessageCallBack(self,
                           channel: pika.adapters.blocking_connection.BlockingChannel,
                           methodFrame: frame.Method,
                           headerFrame: frame.Header,
                           body: bytes,
                           connection: pika.BlockingConnection):
        data = self._CreateDefaultDataHolder(connection, channel)
        data[PikaConstants.DATA_KEY_MESSAGE_HANDLERS] = list(self.messageHandlers())
        incomingMessage = {
            PikaConstants.DATA_KEY_METHOD_FRAME: methodFrame,
            PikaConstants.DATA_KEY_HEADER_FRAME: headerFrame,
            PikaConstants.DATA_KEY_BODY: body,
        }
        data[PikaConstants.DATA_KEY_INCOMING_MESSAGE] = incomingMessage

        pikaBus: AbstractPikaBus = PikaBus.PikaBus(data, closeConnectionOnDelete=False)
        data[PikaConstants.DATA_KEY_BUS] = pikaBus

        pipelineIterator = iter(self._pipeline)
        PikaSteps.HandleNextStep(pipelineIterator, data)

    def _CreateDefaultDataHolder(self,
                                 connection: pika.BlockingConnection,
                                 channel: pika.adapters.blocking_connection.BlockingChannel):
        data = {
            PikaConstants.DATA_KEY_LISTENING_QUEUE: self._listenerQueue,
            PikaConstants.DATA_KEY_DIRECT_EXCHANGE: self._directExchange,
            PikaConstants.DATA_KEY_TOPIC_EXCHANGE: self._topicExchange,
            PikaConstants.DATA_KEY_CONNECTION: connection,
            PikaConstants.DATA_KEY_CHANNEL: channel,
            PikaConstants.DATA_KEY_SERIALIZER: self._pikaSerializer,
            PikaConstants.DATA_KEY_PROPERTY_BUILDER: self._pikaProperties,
            PikaConstants.DATA_KEY_ERROR_HANDLER: self._pikaErrorHandler,
            PikaConstants.DATA_KEY_OUTGOING_MESSAGES: []
        }
        return data

    def _AssertListenerQueueIsSet(self):
        if self._listenerQueue is None:
            raise Exception("Listening queue is not set, so you cannot start the listener process.")
