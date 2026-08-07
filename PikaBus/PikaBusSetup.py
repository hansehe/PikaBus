import asyncio
import atexit
import datetime
import functools
import logging
import random
import signal
import ssl as ssl_module
import uuid
import warnings
from collections import OrderedDict
from typing import Union, Callable, List, Optional

import aio_pika
import aio_pika.exceptions
from yarl import URL

from PikaBus.abstractions.AbstractPikaBusSetup import AbstractPikaBusSetup
from PikaBus.abstractions.AbstractPikaSerializer import AbstractPikaSerializer
from PikaBus.abstractions.AbstractPikaProperties import AbstractPikaProperties
from PikaBus.abstractions.AbstractPikaErrorHandler import AbstractPikaErrorHandler
from PikaBus.abstractions.AbstractPikaMessageHandler import AbstractPikaMessageHandler
from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus
from PikaBus import PikaSerializer, PikaProperties, PikaErrorHandler, PikaBus
from PikaBus.tools import PikaSteps, PikaConstants, PikaTools

_BIND_CACHE_MAX_ENTRIES = 1024


class _ConsumerState:
    """Everything one consumer owns. Replaces the three loose dicts PikaBus 1.x tracked."""

    __slots__ = ('channelId', 'channel', 'queue', 'consumerTag', 'listenerQueue',
                 'ready', 'stopped', 'inflight', 'stopping', 'semaphore', 'boundDestinations')

    def __init__(self, channelId: str, listenerQueue: str, concurrency: int):
        self.channelId = channelId
        self.listenerQueue = listenerQueue
        self.channel: Optional[aio_pika.abc.AbstractChannel] = None
        self.queue: Optional[aio_pika.abc.AbstractQueue] = None
        self.consumerTag: Optional[str] = None
        self.ready = asyncio.Event()
        self.stopped: asyncio.Future = asyncio.get_running_loop().create_future()
        self.inflight: set = set()
        self.stopping = False
        self.semaphore = asyncio.Semaphore(concurrency)
        self.boundDestinations: OrderedDict = OrderedDict()


class PikaBusSetup(AbstractPikaBusSetup):
    def __init__(self,
                 connectionUrl: str = None,
                 *,
                 host: str = 'localhost',
                 port: int = 5672,
                 virtualHost: str = '/',
                 login: str = 'guest',
                 password: str = 'guest',
                 ssl: bool = False,
                 sslContext: ssl_module.SSLContext = None,
                 heartbeat: int = 60,
                 connectionTimeout: float = None,
                 clientProperties: dict = None,
                 connectionKwargs: dict = None,
                 defaultListenerQueue: str = None,
                 defaultSubscriptions: Union[List[str], str] = None,
                 defaultDirectExchange: str = 'PikaBusDirect',
                 defaultTopicExchange: str = 'PikaBusTopic',
                 defaultListenerQueueSettings: dict = None,
                 defaultDirectExchangeSettings: dict = None,
                 defaultTopicExchangeSettings: dict = None,
                 defaultConfirmDelivery: bool = True,
                 defaultPrefetchSize: int = 0,
                 defaultPrefetchCount: int = 10,
                 defaultConsumerCount: int = 1,
                 defaultConcurrency: int = 1,
                 maxDeferredSleep: datetime.timedelta = datetime.timedelta(minutes=5),
                 gracePeriod: float = 30.0,
                 autoBindOnSend: bool = True,
                 pikaSerializer: AbstractPikaSerializer = None,
                 pikaProperties: AbstractPikaProperties = None,
                 pikaErrorHandler: AbstractPikaErrorHandler = None,
                 pikaBusCreateMethod: Callable = None,
                 retryParams: dict = None,
                 stopConsumersAtExit: bool = True,
                 logger=logging.getLogger(__name__)):
        """
        :param str connectionUrl: AMQP url, e.g. 'amqp://guest:guest@localhost:5672/'. Replaces the
            pika.ConnectionParameters of 1.x. If None, one is built from the host/port/login/etc kwargs.
            A supplied url wins outright over those kwargs.
        :param str host: Broker host, used only when connectionUrl is None.
        :param int port: Broker port, used only when connectionUrl is None.
        :param str virtualHost: Virtual host, used only when connectionUrl is None.
        :param str login: Username, used only when connectionUrl is None.
        :param str password: Password, used only when connectionUrl is None.
        :param bool ssl: Connect with amqps, used only when connectionUrl is None.
        :param ssl.SSLContext sslContext: Optional ssl context.
        :param int heartbeat: AMQP heartbeat interval in seconds.
        :param float connectionTimeout: Optional connect timeout in seconds.
        :param dict clientProperties: Optional client properties reported to the broker.
        :param dict connectionKwargs: Extra keyword arguments passed straight to aio_pika.connect_robust,
            e.g. {'fail_fast': False}. The escape hatch for anything aio-pika adds later.
        :param str defaultListenerQueue: Pika default listener queue to receive messages. Set to None to act purely as a publisher.
        :param [str] | str defaultSubscriptions: Default topic or a list of topics to subscribe.
        :param str defaultDirectExchange: Default command exchange to publish direct command messages.
        :param str defaultTopicExchange: Default event exchange to publish event messages.
        :param dict defaultListenerQueueSettings: Default listener queue settings. Empty since 2.0.
            The 1.x default of {'arguments': {'ha-mode': 'all'}} never did anything: classic queue
            mirroring was configured with policies, not queue arguments, and was removed entirely in
            RabbitMq 4.0. For real redundancy use {'arguments': {'x-queue-type': 'quorum'}} - but only
            on a queue that does not exist yet, since x-queue-type is checked on redeclare.
        :param dict defaultDirectExchangeSettings: Default direct exchange settings.
        :param dict defaultTopicExchangeSettings: Default topic exchange settings.
        :param bool defaultConfirmDelivery: Activate confirm delivery with publisher confirms by default
            on all channels. This also enables on_return_raises, so an unroutable mandatory message
            raises instead of being silently dropped.
        :param int defaultPrefetchSize: Prefetch window size. RabbitMq does not implement this, so
            leave it at 0; the parameter exists for signature compatibility.
        :param int defaultPrefetchCount: Prefetch count per consumer channel. Changed from 0 in 1.x,
            which meant *unlimited* - the broker would push an entire backlog into one consumer.
        :param int defaultConsumerCount: Specify default consumer count. Default is 1.
        :param int defaultConcurrency: Max concurrent message handler invocations per consumer.
            Default 1, i.e. serial, which is how 1.x behaved. Raise it only if your handlers are safe
            to run concurrently - doing so also gives up per-queue ordering.
        :param datetime.timedelta maxDeferredSleep: Longest a deferred message waits in-process before
            being handed back to the broker for another hop. Keep this well under RabbitMq's
            consumer_timeout (30 minutes by default).
        :param float gracePeriod: Default seconds to let in-flight handlers finish when stopping.
        :param bool autoBindOnSend: Bind a command destination to the direct exchange the first time
            it is used on a channel. Needed for replies to queues this process did not declare.
        :param AbstractPikaSerializer pikaSerializer: Optional serializer override.
        :param AbstractPikaProperties pikaProperties: Optional properties override.
        :param AbstractPikaErrorHandler pikaErrorHandler: Optional error handler override.
        :param def pikaBusCreateMethod: Optional pikaBus creator method which returns an instance of AbstractPikaBus.
        :param dict retryParams: Consumer restart parameters - tries, delay, max_delay, backoff, jitter.
            All of these are honoured since 2.0; 1.x read only 'tries' and reconnected with no delay.
        :param bool stopConsumersAtExit: Install atexit and SIGINT/SIGTERM handlers that stop consumers.
        :param logging logger: Logging object
        """
        if defaultSubscriptions is None:
            defaultSubscriptions = []
        if defaultListenerQueueSettings is None:
            defaultListenerQueueSettings = {}
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
            retryParams = {}
        retryParams = {**{'tries': -1, 'delay': 1, 'max_delay': 10, 'backoff': 2, 'jitter': 1},
                       **retryParams}

        if defaultConcurrency > 1 and defaultPrefetchCount == 0:
            raise ValueError(
                'defaultPrefetchCount=0 means unlimited prefetch, which combined with '
                'defaultConcurrency>1 lets the broker push an unbounded number of messages into '
                'memory. Set defaultPrefetchCount to at least defaultConcurrency.')
        if 0 < defaultPrefetchCount < defaultConcurrency:
            logger.warning(
                f'defaultPrefetchCount={defaultPrefetchCount} is lower than '
                f'defaultConcurrency={defaultConcurrency}, so concurrency is effectively capped by '
                f'prefetch.')
        if not defaultConfirmDelivery and not autoBindOnSend:
            logger.warning(
                'defaultConfirmDelivery=False together with autoBindOnSend=False means an unroutable '
                'Send is silently discarded with no way to detect it. Enable one of them.')

        self._connectionUrl = self._BuildConnectionUrl(connectionUrl,
                                                       host=host, port=port, virtualHost=virtualHost,
                                                       login=login, password=password, ssl=ssl,
                                                       heartbeat=heartbeat)
        self._sslContext = sslContext
        self._connectionTimeout = connectionTimeout
        self._clientProperties = clientProperties
        self._connectionKwargs = dict(connectionKwargs or {})
        self._defaultListenerQueue = defaultListenerQueue
        self._defaultSubscriptions = defaultSubscriptions
        self._defaultDirectExchange = defaultDirectExchange
        self._defaultTopicExchange = defaultTopicExchange
        self._defaultListenerQueueSettings = defaultListenerQueueSettings
        self._defaultDirectExchangeSettings = defaultDirectExchangeSettings
        self._defaultTopicExchangeSettings = defaultTopicExchangeSettings
        self._defaultConfirmDelivery = defaultConfirmDelivery
        self._defaultPrefetchSize = defaultPrefetchSize
        self._defaultPrefetchCount = defaultPrefetchCount
        self._defaultConsumerCount = defaultConsumerCount
        self._defaultConcurrency = defaultConcurrency
        self._maxDeferredSleep = maxDeferredSleep.total_seconds()
        self._gracePeriod = gracePeriod
        self._autoBindOnSend = autoBindOnSend
        self._pikaSerializer = pikaSerializer
        self._pikaProperties = pikaProperties
        self._pikaErrorHandler = pikaErrorHandler
        self._pikaBusCreateMethod = pikaBusCreateMethod
        self._retryParams = retryParams
        self._logger = logger

        self._pipeline = self._BuildPikaPipeline()
        self._messageHandlers = []
        self._consumers: dict = {}
        self._allConsumingTasks: List[asyncio.Task] = []
        self._connection: Optional[aio_pika.abc.AbstractRobustConnection] = None
        self._connectionLock: Optional[asyncio.Lock] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._consumersRequested = False
        self._closing = False
        self._publisherBindCache: OrderedDict = OrderedDict()
        self._stopConsumersAtExit = stopConsumersAtExit
        self._atexitHook = None
        if stopConsumersAtExit:
            self._atexitHook = functools.partial(PikaBusSetup._AtExit, self)
            atexit.register(self._atexitHook)

    def __del__(self):
        # Closing is asynchronous, and there is no loop to await on during garbage collection, so this
        # only warns. PikaBus 1.x called Stop() here, doing network IO at GC time.
        if self._connection is not None and not self._connection.is_closed:
            warnings.warn(f'Unclosed PikaBusSetup {self!r} - '
                          f'use "async with PikaBusSetup(..) as setup:" or await setup.Close().',
                          ResourceWarning, source=self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, excType, value, traceback):
        await self.Close()

    @property
    def pipeline(self):
        return self._pipeline

    @property
    def connections(self):
        # One robust connection is shared by every channel, so the same object is returned under each
        # channel id. The key space matches 1.x so Stop(channelId=..) still works.
        return {channelId: self._connection for channelId in self._consumers}

    @property
    def channels(self):
        return {channelId: state.channel for channelId, state in self._consumers.items()
                if state.channel is not None}

    @property
    def messageHandlers(self):
        return self._messageHandlers

    @property
    def connection(self):
        """The shared robust connection, or None before the first connect."""
        return self._connection

    async def Init(self,
                   listenerQueue: str = None,
                   listenerQueueSettings: dict = None,
                   topicExchange: str = None,
                   topicExchangeSettings: dict = None,
                   directExchange: str = None,
                   directExchangeSettings: dict = None,
                   subscriptions: Union[List[str], str] = None):
        listenerQueue, listenerQueueSettings = self._GetListenerQueue(listenerQueue, listenerQueueSettings)
        connection = await self._GetConnection()
        channel = await connection.channel(publisher_confirms=self._defaultConfirmDelivery,
                                           on_return_raises=self._defaultConfirmDelivery)
        try:
            await self._CreateDefaultRabbitMqSetup(channel,
                                                   listenerQueue,
                                                   listenerQueueSettings,
                                                   topicExchange,
                                                   topicExchangeSettings,
                                                   directExchange,
                                                   directExchangeSettings,
                                                   subscriptions)
        finally:
            await PikaTools.SafeCloseChannel(channel)

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
                    concurrency: int = None,
                    state: '_ConsumerState' = None):
        if confirmDelivery is None:
            confirmDelivery = self._defaultConfirmDelivery
        if prefetchSize is None:
            prefetchSize = self._defaultPrefetchSize
        if prefetchCount is None:
            prefetchCount = self._defaultPrefetchCount
        if concurrency is None:
            concurrency = self._defaultConcurrency
        listenerQueue, listenerQueueSettings = self._AssertListenerQueueIsSet(listenerQueue, listenerQueueSettings)

        if state is None:
            state = _ConsumerState(str(uuid.uuid1()), listenerQueue, concurrency)
        channelId = state.channelId
        connection = await self._GetConnection()
        channel = await connection.channel(publisher_confirms=confirmDelivery,
                                           on_return_raises=confirmDelivery)
        state.channel = channel
        self._consumers[channelId] = state
        try:
            await channel.set_qos(prefetch_count=prefetchCount, prefetch_size=prefetchSize)
            queue = await self._CreateDefaultRabbitMqSetup(channel,
                                                           listenerQueue,
                                                           listenerQueueSettings,
                                                           topicExchange,
                                                           topicExchangeSettings,
                                                           directExchange,
                                                           directExchangeSettings,
                                                           subscriptions)
            state.queue = queue
            onMessageCallback = functools.partial(self._OnMessageCallBack,
                                                  state=state,
                                                  listenerQueue=listenerQueue,
                                                  topicExchange=topicExchange,
                                                  directExchange=directExchange)
            state.consumerTag = await queue.consume(onMessageCallback)
            state.ready.set()
            self._logger.info(f'Starting new consumer channel with id {channelId} '
                              f'and {len(self._consumers)} ongoing channels.')
            # Resolved by Stop(). This is the only await that lasts; aio-pika's robust connection
            # restores the channel, queue and consumer across a reconnect underneath us.
            await state.stopped
            self._logger.debug(f'Safely stopped consumer channel {channelId}')
        finally:
            state.ready.set()
            await self._TeardownConsumer(state)
            self._consumers.pop(channelId, None)
            self._logger.info(f'Closing consumer channel with id {channelId}.')
            if not state.stopping and not self._closing:
                raise Exception(f'Channel {channelId} stopped unexpectedly.')

    async def Stop(self,
                   channelId: str = None,
                   gracePeriod: float = None):
        if gracePeriod is None:
            gracePeriod = self._gracePeriod
        if channelId is None:
            await asyncio.gather(*[self.Stop(channelId=openChannelId, gracePeriod=gracePeriod)
                                   for openChannelId in list(self._consumers)],
                                 return_exceptions=True)
            return
        state: _ConsumerState = self._consumers.get(channelId, None)
        if state is None or state.stopping:
            return
        state.stopping = True
        self._logger.debug(f'Stopping consumer channel {channelId}')
        await self._CancelConsumer(state)
        await self._DrainInflight(state, gracePeriod)
        if not state.stopped.done():
            state.stopped.set_result(None)

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
                             concurrency: int = None,
                             readyTimeout: float = 30.0):
        listenerQueue, listenerQueueSettings = self._AssertListenerQueueIsSet(listenerQueue, listenerQueueSettings)
        if consumerCount is None:
            consumerCount = self._defaultConsumerCount
        if concurrency is None:
            concurrency = self._defaultConcurrency
        self._consumersRequested = True
        self._closing = False

        states, tasks = [], []
        for _ in range(consumerCount):
            state = _ConsumerState(str(uuid.uuid1()), listenerQueue, concurrency)
            states.append(state)
            task = asyncio.ensure_future(
                self._StartConsumerWithRetryHandler(state=state,
                                                    listenerQueue=listenerQueue,
                                                    listenerQueueSettings=listenerQueueSettings,
                                                    topicExchange=topicExchange,
                                                    topicExchangeSettings=topicExchangeSettings,
                                                    directExchange=directExchange,
                                                    directExchangeSettings=directExchangeSettings,
                                                    subscriptions=subscriptions,
                                                    confirmDelivery=confirmDelivery,
                                                    prefetchSize=prefetchSize,
                                                    prefetchCount=prefetchCount,
                                                    concurrency=concurrency))
            tasks.append(task)

        self._allConsumingTasks += tasks
        self._InstallSignalHandlers()

        # Do not return until every consumer is actually consuming, so a Send() straight afterwards is
        # deterministic. 1.x returned immediately and callers had to sleep.
        try:
            await asyncio.wait_for(
                asyncio.gather(*[state.ready.wait() for state in states]), timeout=readyTimeout)
        except asyncio.TimeoutError:
            for task in tasks:
                if task.done() and not task.cancelled() and task.exception() is not None:
                    raise task.exception()
            raise
        for task in tasks:
            if task.done() and not task.cancelled() and task.exception() is not None:
                raise task.exception()

        return tasks

    async def StopConsumers(self,
                            consumingTasks: List[asyncio.Task] = None,
                            gracePeriod: float = None):
        self._closing = True
        await self.Stop(gracePeriod=gracePeriod)
        await self.WaitUntilStopped(consumingTasks=consumingTasks)
        if consumingTasks is None:
            self._allConsumingTasks = []
        else:
            self._allConsumingTasks = [task for task in self._allConsumingTasks
                                       if task not in consumingTasks]
        self._consumersRequested = bool(self._allConsumingTasks)

    async def WaitUntilStopped(self,
                               consumingTasks: List[asyncio.Task] = None,
                               timeout: float = None):
        if consumingTasks is None:
            consumingTasks = list(self._allConsumingTasks)
        if not consumingTasks:
            return []
        results = await asyncio.wait_for(
            asyncio.gather(*consumingTasks, return_exceptions=True), timeout=timeout)
        for result in results:
            # Surface a consumer that gave up. 1.x resolved such a task successfully, so a dead
            # consumer looked exactly like a cleanly stopped one.
            if isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError):
                raise result
        return results

    def LoopForever(self,
                    consumingTasks: List[asyncio.Task] = None,
                    timeout: float = None):
        """
        Deprecated alias for WaitUntilStopped(), kept for one release.

        Unlike 1.x this does not drive the event loop and shuts nothing down - the caller owns the
        loop now. It must be awaited.
        """
        warnings.warn('LoopForever() is deprecated and will be removed in PikaBus 2.1 - '
                      'await WaitUntilStopped() instead.',
                      DeprecationWarning, stacklevel=2)
        return self.WaitUntilStopped(consumingTasks=consumingTasks, timeout=timeout)

    def CreateBus(self,
                  listenerQueue: str = None,
                  topicExchange: str = None,
                  directExchange: str = None,
                  connection: aio_pika.abc.AbstractConnection = None,
                  confirmDelivery: bool = None):
        """
        Returns an awaitable that is also an async context manager, so both of these work:
            async with pikaBusSetup.CreateBus() as bus: ...
            bus = await pikaBusSetup.CreateBus()
        """
        return _BusFactory(self, listenerQueue, topicExchange, directExchange, connection, confirmDelivery)

    def AddMessageHandler(self, messageHandler: Union[AbstractPikaMessageHandler, Callable]):
        self._messageHandlers.append(messageHandler)

    async def HealthCheck(self,
                          channelId: str = None,
                          allowReconnecting: bool = False):
        connection = self._connection
        if channelId is None:
            if not self._consumers:
                # False only if consumers were asked for and none are running. A publisher-only setup
                # is healthy with no consumers, which is why 1.x returned True here unconditionally.
                return not self._consumersRequested
            return all([await self.HealthCheck(channelId=openChannelId,
                                               allowReconnecting=allowReconnecting)
                        for openChannelId in list(self._consumers)])
        state: _ConsumerState = self._consumers.get(channelId, None)
        if state is None:
            return False
        if connection is None or connection.is_closed:
            return False
        if not allowReconnecting and not connection.connected.is_set():
            return False
        if state.channel is None or state.channel.is_closed:
            return False
        if state.consumerTag is None or state.stopped.done():
            return False
        return True

    async def QueueMessagesCount(self,
                                 queue: str = None,
                                 channel: aio_pika.abc.AbstractChannel = None):
        if queue is None:
            queue = self._defaultListenerQueue
        if queue is None:
            raise Exception('Cannot count messages without a queue.')
        if channel is not None:
            return await PikaTools.GetQueueMessagesCount(channel, queue)
        # A passive declare of a missing queue is a channel-level error, so it gets a channel of its
        # own rather than killing one the caller still needs.
        connection = await self._GetConnection()
        temporaryChannel = await connection.channel(publisher_confirms=False)
        try:
            return await PikaTools.GetQueueMessagesCount(temporaryChannel, queue)
        finally:
            await PikaTools.SafeCloseChannel(temporaryChannel)

    async def Close(self):
        self._closing = True
        try:
            await self.Stop()
            await self.WaitUntilStopped()
        except Exception as exception:
            self._logger.debug(f'Ignoring failure while stopping consumers on close - '
                               f'{str(type(exception))}: {str(exception)}')
        self._allConsumingTasks = []
        self._consumersRequested = False
        self._publisherBindCache.clear()
        if self._connection is not None:
            await PikaTools.SafeCloseConnection(self._connection)
            self._connection = None
        if self._atexitHook is not None:
            atexit.unregister(self._atexitHook)
            self._atexitHook = None

    # ------------------------------------------------------------------ internals

    def _BuildConnectionUrl(self, connectionUrl: str,
                            host: str, port: int, virtualHost: str,
                            login: str, password: str, ssl: bool, heartbeat: int):
        if connectionUrl is not None:
            return connectionUrl
        return URL.build(
            scheme='amqps' if ssl else 'amqp',
            host=host,
            port=port,
            user=login,
            password=password,
            path=virtualHost if virtualHost.startswith('/') else f'/{virtualHost}',
            query={'heartbeat': str(heartbeat)})

    async def _GetConnection(self) -> aio_pika.abc.AbstractRobustConnection:
        runningLoop = asyncio.get_running_loop()
        if self._connectionLock is None:
            self._connectionLock = asyncio.Lock()
            self._loop = runningLoop
        elif self._loop is not runningLoop:
            raise RuntimeError(
                'This PikaBusSetup is bound to a different event loop than the one running now. '
                'Create one PikaBusSetup per event loop - do not share an instance across '
                'asyncio.run() calls or across IsolatedAsyncioTestCase test methods.')
        async with self._connectionLock:
            if self._connection is not None and not self._connection.is_closed:
                return self._connection
            self._logger.debug(f'Connecting to {self._connectionUrl}')
            self._connection = await aio_pika.connect_robust(
                self._connectionUrl,
                ssl_context=self._sslContext,
                timeout=self._connectionTimeout,
                client_properties=self._clientProperties,
                # aio-pika reconnects on this interval by itself; sharing the retry delay keeps the
                # two layers on one cadence.
                reconnect_interval=self._retryParams['delay'],
                **self._connectionKwargs)
            # Server-side bindings survive a reconnect, but a rebuilt cluster or a fresh vhost would
            # not have them, and a stale cache would hide that forever.
            self._connection.reconnect_callbacks.add(
                lambda _sender, *_args: self._publisherBindCache.clear())
            return self._connection

    async def _StartConsumerWithRetryHandler(self,
                                             state: _ConsumerState,
                                             listenerQueue: str,
                                             listenerQueueSettings: dict,
                                             topicExchange: str,
                                             topicExchangeSettings: dict,
                                             directExchange: str,
                                             directExchangeSettings: dict,
                                             subscriptions: Union[List[str], str],
                                             confirmDelivery: bool = None,
                                             prefetchSize: int = None,
                                             prefetchCount: int = None,
                                             concurrency: int = None):
        """
        Restart a consumer that failed for a reason aio-pika's robust connection cannot fix - bad
        credentials, a missing vhost, a failed declare, or the broker cancelling the consumer.

        Transport loss is *not* handled here: connect_robust reconnects and restores the channel,
        queue and consumer underneath Start(), which therefore never returns. Retrying here as well
        would produce two consumers per intended consumer.

        Unlike 1.x, this honours every retryParams key. 1.x read only 'tries' and looped with no
        delay at all, hammering a down broker as fast as the socket would allow.
        """
        tries = self._retryParams['tries']
        delay = self._retryParams['delay']
        maxDelay = self._retryParams['max_delay']
        backoff = self._retryParams['backoff']
        jitter = self._retryParams['jitter']
        lastError = None
        while tries != 0:
            self._logger.debug(f'Starting consumer with {tries} tries (-1 = infinite) left')
            try:
                await self.Start(listenerQueue=listenerQueue,
                                 listenerQueueSettings=listenerQueueSettings,
                                 topicExchange=topicExchange,
                                 topicExchangeSettings=topicExchangeSettings,
                                 directExchange=directExchange,
                                 directExchangeSettings=directExchangeSettings,
                                 subscriptions=subscriptions,
                                 confirmDelivery=confirmDelivery,
                                 prefetchSize=prefetchSize,
                                 prefetchCount=prefetchCount,
                                 concurrency=concurrency,
                                 state=state)
                return
            except asyncio.CancelledError:
                raise
            except Exception as exception:
                lastError = exception
                self._logger.warning(f'Failed consumer: {str(type(exception))}: {str(exception)}')
            if state.stopping or self._closing:
                return
            if tries > 0:
                tries -= 1
            if tries == 0:
                break
            # Fresh state for the next attempt - the old one's future is already resolved.
            state = self._ResetConsumerState(state, concurrency)
            await asyncio.sleep(delay)
            delay = min(delay * backoff + random.uniform(0, jitter), maxDelay)
        state.ready.set()
        if lastError is not None:
            raise lastError

    def _ResetConsumerState(self, state: _ConsumerState, concurrency: int) -> _ConsumerState:
        newState = _ConsumerState(state.channelId, state.listenerQueue, concurrency)
        return newState

    async def _CancelConsumer(self, state: _ConsumerState):
        if state.queue is None or state.consumerTag is None:
            return
        try:
            await state.queue.cancel(state.consumerTag)
        except Exception as exception:
            self._logger.debug(f'Ignoring failure cancelling consumer {state.channelId} - '
                               f'{str(type(exception))}: {str(exception)}')

    async def _DrainInflight(self, state: _ConsumerState, gracePeriod: float):
        if not state.inflight:
            return
        pending = list(state.inflight)
        self._logger.debug(f'Waiting up to {gracePeriod}s for {len(pending)} in-flight message(s) '
                           f'on channel {state.channelId}')
        try:
            await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True),
                                   timeout=gracePeriod)
        except asyncio.TimeoutError:
            self._logger.warning(
                f'{len([task for task in pending if not task.done()])} message handler(s) on channel '
                f'{state.channelId} did not finish within {gracePeriod}s and were cancelled. '
                f'Those messages were not acknowledged, so the broker will redeliver them.')
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    async def _TeardownConsumer(self, state: _ConsumerState):
        await self._CancelConsumer(state)
        await self._DrainInflight(state, self._gracePeriod)
        # After draining, never before: aio-pika parents the per-delivery tasks on the channel, so
        # closing it first would abandon handlers mid-transaction.
        await PikaTools.SafeCloseChannel(state.channel)

    async def _CreateDefaultRabbitMqSetup(self,
                                          channel: aio_pika.abc.AbstractChannel,
                                          listenerQueue: str,
                                          listenerQueueSettings: dict,
                                          topicExchange: str = None,
                                          topicExchangeSettings: dict = None,
                                          directExchange: str = None,
                                          directExchangeSettings: dict = None,
                                          subscriptions: Union[List[str], str] = None):
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
        directExchangeObject = await PikaTools.CreateExchange(channel, directExchange,
                                                             settings=directExchangeSettings)
        await PikaTools.CreateExchange(channel, topicExchange, settings=topicExchangeSettings)
        if listenerQueue is None:
            return None
        queue = await PikaTools.CreateDurableQueue(channel, listenerQueue,
                                                  settings=listenerQueueSettings)
        # Bind to the direct exchange here, which 1.x never did - it relied on BasicSend binding the
        # destination on every single send. Doing it once at declare time is what makes removing that
        # per-message bind safe.
        await PikaTools.BindQueue(queue, directExchangeObject, listenerQueue)
        await PikaTools.BasicSubscribe(queue, topicExchange, subscriptions)
        return queue

    def _BuildPikaPipeline(self):
        pipeline = [
            PikaSteps.TryHandleMessageInPipeline,
            PikaSteps.CheckIfMessageIsDeferred,
            PikaSteps.SerializeMessage,
            PikaSteps.HandleMessage,
            PikaSteps.AcknowledgeMessage,
        ]
        return pipeline

    async def _BindDestination(self, cache: OrderedDict,
                               channel: aio_pika.abc.AbstractChannel,
                               exchange: str, destination: str):
        """
        Bind a command destination to the direct exchange, at most once per cache.

        Needed because Reply() targets whatever queue the incoming ReplyToAddress header names - a
        queue this process may never have declared. 1.x re-bound it on every send.
        """
        key = (exchange, destination)
        if key in cache:
            cache.move_to_end(key)
            return
        queue = await channel.get_queue(destination, ensure=False)
        await PikaTools.BindQueue(queue, exchange, destination)
        cache[key] = True
        while len(cache) > _BIND_CACHE_MAX_ENTRIES:
            cache.popitem(last=False)

    async def _OnMessageCallBack(self,
                                 message: aio_pika.abc.AbstractIncomingMessage,
                                 state: _ConsumerState,
                                 listenerQueue: str,
                                 topicExchange: str = None,
                                 directExchange: str = None):
        # aio-pika creates one task per delivery, so this runs concurrently up to prefetch. The
        # semaphore is what makes the default (concurrency=1) serial, matching 1.x.
        task = asyncio.current_task()
        if task is not None:
            state.inflight.add(task)
        try:
            async with state.semaphore:
                await self._HandleMessage(message, state, listenerQueue,
                                          topicExchange=topicExchange,
                                          directExchange=directExchange)
        except asyncio.CancelledError:
            raise
        except BaseException as exception:
            # Outermost guard. aio-pika owns this task, so anything escaping here would surface only
            # as an "exception was never retrieved" warning at garbage collection time.
            self._logger.exception(
                f'Unhandled failure in message callback on channel {state.channelId} - '
                f'{str(type(exception))}: {str(exception)}')
        finally:
            if task is not None:
                state.inflight.discard(task)

    async def _HandleMessage(self,
                             message: aio_pika.abc.AbstractIncomingMessage,
                             state: _ConsumerState,
                             listenerQueue: str,
                             topicExchange: str = None,
                             directExchange: str = None):
        channelId = state.channelId
        try:
            self._logger.debug(f"Received new message on channel {channelId}")
            data = self._CreateDefaultDataHolder(self._connection, state.channel, listenerQueue,
                                                 topicExchange=topicExchange,
                                                 directExchange=directExchange,
                                                 channelId=channelId,
                                                 bindCache=state.boundDestinations)
            data[PikaConstants.DATA_KEY_MESSAGE_HANDLERS] = list(self.messageHandlers)
            incomingMessage = {
                PikaConstants.DATA_KEY_MESSAGE: message,
                # A copy, so the pipeline and error handler never mutate aio-pika's own header dict.
                PikaConstants.DATA_KEY_HEADERS: dict(message.headers or {}),
                PikaConstants.DATA_KEY_BODY: message.body,
                # Deprecated 1.x compatibility shim; warns when touched.
                PikaConstants.DATA_KEY_HEADER_FRAME: PikaTools.DeprecatedHeaderFrame(message),
            }
            data[PikaConstants.DATA_KEY_INCOMING_MESSAGE] = incomingMessage

            pikaBus: AbstractPikaBus = self._pikaBusCreateMethod(data=data,
                                                                 closeChannelOnExit=False,
                                                                 closeConnectionOnExit=False)
            data[PikaConstants.DATA_KEY_BUS] = pikaBus

            pipelineIterator = iter(self._pipeline)
            await PikaSteps.HandleNextStep(pipelineIterator, data)
            self._logger.debug(f"Successfully handled message on channel {channelId}")
        except Exception as exception:
            self._logger.exception(f"Failed handling message on channel {channelId} - {str(exception)}")
            await self._HandleDoubleFault(message, state, exception)

    async def _HandleDoubleFault(self,
                                 message: aio_pika.abc.AbstractIncomingMessage,
                                 state: _ConsumerState,
                                 exception: Exception):
        """
        Last resort: the pipeline raised *and* the error handler could not deal with it.

        1.x nacked with requeue=True (pika's default), so a poison message came straight back and
        looped forever. A flat requeue=False is not right either - the usual reason to get here is
        transient (the error queue was briefly unreachable, the node failed over), and discarding
        would lose the message for good. So: requeue once, then stop.
        """
        channel = state.channel
        if channel is None or channel.is_closed or \
                self._connection is None or self._connection.is_closed:
            # Nothing can be acked or rejected on a dead channel, and the broker requeues every
            # unacked delivery when it closes. Attempting it would just raise again and bury the
            # original error.
            self._logger.error(
                f'Cannot reject message on channel {state.channelId} - the channel is closed. '
                f'The broker will redeliver it.')
            return
        if message.processed:
            return
        requeue = not message.redelivered
        await PikaTools.SafeRejectMessage(message, requeue=requeue, logger=self._logger)
        if not requeue:
            self._logger.error(
                f'Message was already redelivered and failed again, including its error handling. '
                f'Rejecting without requeue - it is discarded unless the queue declares '
                f'x-dead-letter-exchange. Original failure - {str(type(exception))}: {str(exception)}')

    def _CreateDefaultDataHolder(self,
                                 connection: aio_pika.abc.AbstractRobustConnection,
                                 channel: aio_pika.abc.AbstractChannel,
                                 listenerQueue: str,
                                 topicExchange: str = None,
                                 directExchange: str = None,
                                 channelId: str = None,
                                 bindCache: OrderedDict = None):
        if topicExchange is None:
            topicExchange = self._defaultTopicExchange
        if directExchange is None:
            directExchange = self._defaultDirectExchange
        binder = None
        if self._autoBindOnSend:
            cache = self._publisherBindCache if bindCache is None else bindCache
            binder = functools.partial(self._BindDestination, cache)
        data = {
            PikaConstants.DATA_KEY_LISTENER_QUEUE: listenerQueue,
            PikaConstants.DATA_KEY_DIRECT_EXCHANGE: directExchange,
            PikaConstants.DATA_KEY_TOPIC_EXCHANGE: topicExchange,
            PikaConstants.DATA_KEY_CONNECTION: connection,
            PikaConstants.DATA_KEY_CHANNEL: channel,
            PikaConstants.DATA_KEY_CHANNEL_ID: channelId,
            PikaConstants.DATA_KEY_SERIALIZER: self._pikaSerializer,
            PikaConstants.DATA_KEY_PROPERTY_BUILDER: self._pikaProperties,
            PikaConstants.DATA_KEY_ERROR_HANDLER: self._pikaErrorHandler,
            PikaConstants.DATA_KEY_LOGGER: self._logger,
            PikaConstants.DATA_KEY_MAX_DEFERRED_SLEEP: self._maxDeferredSleep,
            PikaConstants.DATA_KEY_BIND_CACHE: binder,
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
            self._logger.error(msg)
            raise Exception(msg)
        return listenerQueue, listenerQueueSettings

    def _DefaultPikaBusCreator(self, data: dict,
                               closeChannelOnExit: bool = False,
                               closeConnectionOnExit: bool = False):
        return PikaBus.PikaBus(data=data,
                               closeChannelOnExit=closeChannelOnExit,
                               closeConnectionOnExit=closeConnectionOnExit,
                               logger=self._logger)

    def _InstallSignalHandlers(self):
        """
        Stop consumers on SIGINT/SIGTERM.

        1.x polled threading.main_thread().is_alive() from the heartbeat thread, which never saw
        SIGTERM at all - so a container stop killed in-flight messages outright.
        """
        if not self._stopConsumersAtExit or self._loop is None:
            return
        for sig in (getattr(signal, 'SIGINT', None), getattr(signal, 'SIGTERM', None)):
            if sig is None:
                continue
            try:
                self._loop.add_signal_handler(
                    sig, lambda: asyncio.ensure_future(self.Close()))
            except (NotImplementedError, RuntimeError, ValueError):
                # add_signal_handler is not available on Windows, and only works on the main thread.
                pass

    @staticmethod
    def _AtExit(setup: 'PikaBusSetup'):
        if setup._connection is None or setup._connection.is_closed:
            return
        loop = setup._loop
        if loop is None or loop.is_closed() or loop.is_running():
            warnings.warn(f'PikaBusSetup was not closed before exit - '
                          f'await setup.Close() or use "async with PikaBusSetup(..)".',
                          ResourceWarning)
            return
        try:
            loop.run_until_complete(setup.Close())
        except Exception:
            pass


class _BusFactory:
    """
    Makes CreateBus() usable both as `async with` and as a plain `await`.

    A bus needs a channel, and opening one is asynchronous, so CreateBus() cannot simply return a bus.
    """

    __slots__ = ('_setup', '_listenerQueue', '_topicExchange', '_directExchange',
                 '_connection', '_confirmDelivery', '_bus')

    def __init__(self, setup: PikaBusSetup,
                 listenerQueue: str = None,
                 topicExchange: str = None,
                 directExchange: str = None,
                 connection: aio_pika.abc.AbstractConnection = None,
                 confirmDelivery: bool = None):
        self._setup = setup
        self._listenerQueue = listenerQueue
        self._topicExchange = topicExchange
        self._directExchange = directExchange
        self._connection = connection
        self._confirmDelivery = confirmDelivery
        self._bus: Optional[AbstractPikaBus] = None

    async def _Create(self) -> AbstractPikaBus:
        setup = self._setup
        confirmDelivery = self._confirmDelivery
        if confirmDelivery is None:
            confirmDelivery = setup._defaultConfirmDelivery

        closeConnectionOnExit = False
        connection = self._connection
        if connection is None:
            connection = await setup._GetConnection()
        channel = await connection.channel(publisher_confirms=confirmDelivery,
                                           on_return_raises=confirmDelivery)

        listenerQueue, _ = setup._GetListenerQueue(self._listenerQueue)
        data = setup._CreateDefaultDataHolder(connection, channel, listenerQueue,
                                              topicExchange=self._topicExchange,
                                              directExchange=self._directExchange)
        self._bus = setup._pikaBusCreateMethod(data=data,
                                               closeChannelOnExit=True,
                                               closeConnectionOnExit=closeConnectionOnExit)
        return self._bus

    def __await__(self):
        return self._Create().__await__()

    async def __aenter__(self) -> AbstractPikaBus:
        bus = await self._Create()
        return await bus.__aenter__()

    async def __aexit__(self, excType, value, traceback):
        if self._bus is None:
            return
        return await self._bus.__aexit__(excType, value, traceback)
