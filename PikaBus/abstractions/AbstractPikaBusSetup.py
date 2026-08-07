import abc
import asyncio
from typing import Union, Callable, List

from PikaBus.abstractions.AbstractPikaMessageHandler import AbstractPikaMessageHandler


class AbstractPikaBusSetup(abc.ABC):
    """
    Owns the connection, the consumers and the message pipeline.

    Changed in 2.0: asyncio-native throughout. Every method that talks to the broker is a coroutine,
    and the `loop` / `executor` parameters are gone - the caller owns the event loop.

        async with PikaBusSetup('amqp://amqp:amqp@localhost:5672/',
                                defaultListenerQueue='myQueue') as pikaBusSetup:
            pikaBusSetup.AddMessageHandler(MessageHandlerMethod)
            await pikaBusSetup.StartConsumers()
            await pikaBusSetup.WaitUntilStopped()

    An instance is bound to the event loop it first connected on. Do not share one across
    asyncio.run() calls or across unittest.IsolatedAsyncioTestCase test methods.
    """

    @property
    @abc.abstractmethod
    def pipeline(self):
        """
        returns pipeline [list]: A list of function steps to go through when handling a message.
        Each step may be `async def` or plain `def`, and must have these parameters:
        - pipelineIterator: iter
        - data: dict
        Each step is responsible for awaiting PikaSteps.HandleNextStep(pipelineIterator, data)
        to continue the pipeline.
        """
        pass

    @property
    @abc.abstractmethod
    def connections(self):
        """
        returns all open connections as a dictionary with keys as the channel ids.

        Note: PikaBus 2.0 multiplexes every channel over a single robust connection, so the same
        connection object is returned under each channel id. The key space is kept identical to 1.x
        so that Stop(channelId=..) and HealthCheck(channelId=..) still work.
        :rtype: dict{id: aio_pika.abc.AbstractRobustConnection}
        """
        pass

    @property
    @abc.abstractmethod
    def channels(self):
        """
        returns all open channels as a dictionary with keys as the channel ids.
        :rtype: dict{id: aio_pika.abc.AbstractChannel}
        """
        pass

    @property
    @abc.abstractmethod
    def messageHandlers(self):
        """
        returns all registered message handlers.
        :rtype: list[AbstractPikaMessageHandler]
        """
        pass

    @abc.abstractmethod
    async def Init(self,
                   listenerQueue: str = None,
                   listenerQueueSettings: dict = None,
                   topicExchange: str = None,
                   topicExchangeSettings: dict = None,
                   directExchange: str = None,
                   directExchangeSettings: dict = None,
                   subscriptions: Union[List[str], str] = None):
        """
        Initialize RabbitMq without starting a consumer, by creating exchanges and the listener queue.

        Since 2.0 this also binds the listener queue to the direct exchange, so the queue is
        addressable with Send() without a per-message bind.

        :param str listenerQueue: Optional listener queue to override default listener queue.
        :param dict listenerQueueSettings: Optional listener queue settings.
        :param str topicExchange: Optional topic exchange to override default topic exchange.
        :param dict topicExchangeSettings: Optional topic exchange settings.
        :param str directExchange: Optional direct exchange to override default direct exchange.
        :param dict directExchangeSettings: Optional direct exchange settings.
        :param [str] | str subscriptions: Optional topic or a list of topics to subscribe, overriding default topic subscriptions.
        """
        pass

    @abc.abstractmethod
    async def Start(self,
                    listenerQueue: str = None,
                    listenerQueueSettings: dict = None,
                    topicExchange: str = None,
                    topicExchangeSettings: dict = None,
                    directExchange: str = None,
                    directExchangeSettings: dict = None,
                    subscriptions: Union[List[str], str] = None,
                    confirmDelivery: bool = None,
                    prefetchSize: int = None,
                    prefetchCount: int = None,
                    concurrency: int = None):
        """
        Start one consumer and await until it is stopped.

        Returns normally only when the consumer was stopped on request. Any other outcome raises, so a
        consumer that dies can never be mistaken for one that finished cleanly.

        :param str listenerQueue: Optional listener queue to override default listener queue.
        :param dict listenerQueueSettings: Optional listener queue settings.
        :param str topicExchange: Optional topic exchange to override default topic exchange.
        :param dict topicExchangeSettings: Optional topic exchange settings.
        :param str directExchange: Optional direct exchange to override default direct exchange.
        :param dict directExchangeSettings: Optional direct exchange settings.
        :param [str] | str subscriptions: Optional topic or a list of topics to subscribe, overriding default topic subscriptions.
        :param bool confirmDelivery: Activate confirm delivery with publisher confirms on the channel.
        :param int prefetchSize: Specify prefetch window size. 0 means it is deactivated. RabbitMq does not implement this.
        :param int prefetchCount: Specify prefetch count for the channel.
        :param int concurrency: Max concurrent message handler invocations for this consumer. 1 means serial.
        """
        pass

    @abc.abstractmethod
    async def Stop(self,
                   channelId: str = None,
                   gracePeriod: float = None):
        """
        Stop one or all consumers, letting in-flight messages finish first.

        The `forceCloseChannel` parameter from 1.x is gone - PikaBus now tracks intentional stops
        internally, which is what that flag existed to signal.

        :param str channelId: Optional channel id. Get open channels with self.channels.
        :param float gracePeriod: Seconds to wait for in-flight message handlers before cancelling them.
        """
        pass

    @abc.abstractmethod
    async def StartConsumers(self,
                             consumerCount: int = None,
                             listenerQueue: str = None,
                             listenerQueueSettings: dict = None,
                             topicExchange: str = None,
                             topicExchangeSettings: dict = None,
                             directExchange: str = None,
                             directExchangeSettings: dict = None,
                             subscriptions: Union[List[str], str] = None,
                             confirmDelivery: bool = None,
                             prefetchSize: int = None,
                             prefetchCount: int = None,
                             concurrency: int = None):
        """
        Start consumers as asyncio tasks.

        Since 2.0 this does not return until every consumer is actually consuming, so a Send() issued
        immediately afterwards is deterministic. In 1.x it returned early and the caller had to sleep.

        :param int consumerCount: Optional number of consumers to start to override default consumer count.
        :rtype: [asyncio.Task]
        """
        pass

    @abc.abstractmethod
    async def StopConsumers(self,
                            consumingTasks: List[asyncio.Task] = None,
                            gracePeriod: float = None):
        """
        Stop consumers and wait until they are stopped.

        Idempotent, and restartable: StartConsumers() works again afterwards. In 1.x this permanently
        poisoned the instance, because it shut down the shared thread pool executor.

        :param List[asyncio.Task] consumingTasks: Optional tasks returned by StartConsumers(..).
        :param float gracePeriod: Seconds to wait for in-flight message handlers before cancelling them.
        """
        pass

    @abc.abstractmethod
    async def WaitUntilStopped(self,
                               consumingTasks: List[asyncio.Task] = None,
                               timeout: float = None):
        """
        Await the consumers until they stop. Replaces LoopForever() from 1.x.

        Re-raises the first consumer failure, so a consumer that gave up does not fail silently.

        :param List[asyncio.Task] consumingTasks: Optional tasks returned by StartConsumers(..).
        :param float timeout: Optional timeout in seconds.
        """
        pass

    @abc.abstractmethod
    def CreateBus(self,
                  listenerQueue: str = None,
                  topicExchange: str = None,
                  directExchange: str = None,
                  connection=None,
                  confirmDelivery: bool = None):
        """
        Create a bus with its own channel.

        Returns an async context manager, so the idiomatic use is:
            async with pikaBusSetup.CreateBus() as bus:
                await bus.Publish(payload=payload, topic='myTopic')

        Awaiting it directly also works, for a bus not scoped to a block:
            bus = await pikaBusSetup.CreateBus()
            ...
            await bus.Close()

        :param str listenerQueue: Optional listener queue to override default listener queue.
        :param str topicExchange: Optional topic exchange to override default topic exchange.
        :param str directExchange: Optional direct exchange to override default direct exchange.
        :param aio_pika.abc.AbstractConnection connection: Optional connection to reuse an open connection.
        :param confirmDelivery: Optionally set publisher confirms to override default setup.
        :rtype: PikaBus.abstractions.AbstractPikaBus.AbstractPikaBus
        """
        pass

    @abc.abstractmethod
    def AddMessageHandler(self, messageHandler: Union[AbstractPikaMessageHandler, Callable]):
        """
        :param AbstractPikaMessageHandler | def messageHandler: An abstract message handler class, or a
            method with `**kwargs` input. Either may be `async def`. A synchronous handler cannot
            publish, since the bus methods are coroutines.
        """
        pass

    @abc.abstractmethod
    async def HealthCheck(self,
                          channelId: str = None,
                          allowReconnecting: bool = False):
        """
        Verify consumer health.

        Changed in 2.0 to report something meaningful. It now checks that the consumer is actually
        registered and its task is alive, not merely that the channel object exists. It also returns
        False - rather than 1.x's unconditional True - when consumers were requested but none are
        running, and for an unknown channel id.

        Treat this as a readiness probe: it is legitimately False for a few seconds during a
        reconnect. Pass allowReconnecting=True for a liveness probe that tolerates that.

        :param str channelId: Optional channel id. Get open channels with self.channels.
        :param bool allowReconnecting: Report healthy while the connection is recovering.
        :rtype: bool
        """
        pass

    @abc.abstractmethod
    async def QueueMessagesCount(self,
                                 queue: str = None,
                                 channel=None):
        """
        Raises aiormq.exceptions.ChannelNotFoundEntity if the queue does not exist, rather than
        reporting it as empty - an absent queue and an empty one are different problems.

        :param str queue: Optional queue. Default listener queue is used by default.
        :param aio_pika.abc.AbstractChannel channel: Optional channel. A temporary channel is used by
            default, because a passive declare of a missing queue is a channel-level error that would
            otherwise kill a channel the caller still needs. Pass a channel only if you are willing
            to lose it should the queue be missing.
        :rtype: int
        """
        pass

    @abc.abstractmethod
    async def Close(self):
        """
        Stop every consumer and close all channels and the connection. Idempotent.
        Added in 2.0, replacing the 1.x __del__ which did network IO during garbage collection.
        """
        pass
