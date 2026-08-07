import asyncio
import inspect
import logging
import warnings
from typing import Any, Callable, List, Union

import aio_pika
import aio_pika.exceptions
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractQueue, AbstractRobustConnection
from pamqp import commands as pamqp_commands


async def CallMaybeAwaitable(func: Callable, *args, **kwargs):
    """
    Call `func` and await the result if it is awaitable.

    This is what lets PikaBus accept both `async def` and plain `def` message handlers and
    pipeline steps. It deliberately inspects the *returned value* rather than using
    `inspect.iscoroutinefunction(func)`, because the latter is False for functools.partial,
    for objects with an `async def __call__`, and for many decorated handlers.

    :param def func: Any callable, synchronous or asynchronous.
    :rtype: The return value of func, with coroutines resolved.
    """
    result = func(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


async def CreateDurableQueue(channel: AbstractChannel, queue: str,
                             settings: dict = None) -> AbstractQueue:
    """
    :param aio_pika.abc.AbstractChannel channel: Open channel.
    :param str queue: Queue name.
    :param dict settings: Optional queue settings - passive, durable, exclusive, auto_delete, arguments.
    :rtype: aio_pika.abc.AbstractQueue
    """
    if settings is None:
        settings = {}
    return await channel.declare_queue(queue,
                                       passive=settings.get('passive', False),
                                       durable=settings.get('durable', True),
                                       exclusive=settings.get('exclusive', False),
                                       auto_delete=settings.get('auto_delete', False),
                                       arguments=settings.get('arguments', None))


async def CreateExchange(channel: AbstractChannel, exchange: str,
                         settings: dict = None) -> AbstractExchange:
    """
    :param aio_pika.abc.AbstractChannel channel: Open channel.
    :param str exchange: Exchange name.
    :param dict settings: Optional exchange settings - exchange_type, passive, durable, auto_delete, internal, arguments.
    :rtype: aio_pika.abc.AbstractExchange
    """
    if settings is None:
        settings = {}
    return await channel.declare_exchange(exchange,
                                          type=settings.get('exchange_type', 'direct'),
                                          passive=settings.get('passive', False),
                                          durable=settings.get('durable', True),
                                          auto_delete=settings.get('auto_delete', False),
                                          internal=settings.get('internal', False),
                                          arguments=settings.get('arguments', None))


async def BindQueue(queue: AbstractQueue, exchange: Union[AbstractExchange, str], topic: str,
                    arguments: dict = None):
    """
    :param aio_pika.abc.AbstractQueue queue: Declared queue.
    :param aio_pika.abc.AbstractExchange | str exchange: Exchange or exchange name.
    :param str topic: Routing key.
    :param dict arguments: Optional binding arguments.
    """
    await queue.bind(exchange, routing_key=topic, arguments=arguments)


async def UnbindQueue(queue: AbstractQueue, exchange: Union[AbstractExchange, str], topic: str,
                      arguments: dict = None):
    """
    :param aio_pika.abc.AbstractQueue queue: Declared queue.
    :param aio_pika.abc.AbstractExchange | str exchange: Exchange or exchange name.
    :param str topic: Routing key.
    :param dict arguments: Optional binding arguments.
    """
    await queue.unbind(exchange, routing_key=topic, arguments=arguments)


async def AssertDurableQueueExists(channel: AbstractChannel, queue: str,
                                   retries: int = 0,
                                   logger=logging.getLogger(__name__)):
    """
    Verify that a durable queue exists, with an optional retry.

    PikaBus no longer calls this on the send path - publisher confirms with mandatory delivery
    report an unroutable destination in a single round trip instead. It is kept as a public
    helper for callers who want an explicit up-front check.

    Note the passive declare uses robust=False on purpose: a RobustChannel replays every
    declare it has seen after a reconnect, so a passive declare of a queue that is later
    deleted would make channel recovery fail forever.

    :param aio_pika.abc.AbstractChannel channel: Open channel.
    :param str queue: Queue name.
    :param int retries: Number of retries, one second apart.
    :param logging logger: Logging object.
    """
    count = 0
    while count <= retries:
        try:
            await channel.declare_queue(queue, durable=True, passive=True, robust=False)
            return
        except Exception:
            count += 1
            if count <= retries:
                await asyncio.sleep(1)
    msg = f"Queue {queue} does not exist!"
    logger.error(msg)
    raise Exception(msg)


async def GetQueueMessagesCount(channel: AbstractChannel, queue: str) -> int:
    """
    :param aio_pika.abc.AbstractChannel channel: Open channel.
    :param str queue: Queue name.
    :rtype: int - message count, or -1 if the channel is closed.
    """
    if channel.is_closed:
        return -1
    declaredQueue = await channel.declare_queue(queue, passive=True, robust=False)
    return declaredQueue.declaration_result.message_count


async def SafeCloseChannel(channel: AbstractChannel, acceptAllFailures: bool = True):
    """
    :param aio_pika.abc.AbstractChannel channel: Channel to close.
    :param bool acceptAllFailures: Swallow any close failure.
    """
    if channel is None or channel.is_closed:
        return
    try:
        await channel.close()
    except aio_pika.exceptions.ChannelInvalidStateError:
        # channel already closed
        pass
    except Exception:
        if not acceptAllFailures:
            raise


async def SafeCloseConnection(connection: AbstractRobustConnection, acceptAllFailures: bool = True):
    """
    :param aio_pika.abc.AbstractRobustConnection connection: Connection to close.
    :param bool acceptAllFailures: Swallow any close failure.
    """
    if connection is None or connection.is_closed:
        return
    try:
        await connection.close()
    except aio_pika.exceptions.ConnectionClosed:
        # connection already closed
        pass
    except Exception:
        if not acceptAllFailures:
            raise


async def BasicPublish(exchange: AbstractExchange, routingKey: str, message: aio_pika.Message,
                       mandatory: bool = True):
    """
    Publish a message and verify the broker acknowledged it.

    With publisher confirms enabled the channel is created with on_return_raises=True, so an
    unroutable mandatory message raises aio_pika.exceptions.DeliveryError. The explicit Ack check
    below is a second line of defence for brokers or channels where a return is reported by
    resolving the confirmation instead of raising.

    :param aio_pika.abc.AbstractExchange exchange: Exchange to publish on.
    :param str routingKey: Topic or destination queue name.
    :param aio_pika.Message message: Message to publish.
    :param bool mandatory: Mandatory delivery to at least one queue.
    """
    confirmation = await exchange.publish(message, routing_key=routingKey, mandatory=mandatory)
    if mandatory and confirmation is not None and \
            not isinstance(confirmation, pamqp_commands.Basic.Ack):
        raise aio_pika.exceptions.DeliveryError(None, confirmation)


def NormalizeTopics(topic: Union[List[str], str], arguments: dict = None):
    """
    Normalize the accepted topic shapes into a list of (topic, arguments) pairs.

    Accepts a single topic, a list of topics, and dict entries of the
    form {'topic': str, 'arguments': dict} - all supported since PikaBus 1.x.

    :param str | [str] topic: Topic or topics.
    :param dict arguments: Default binding arguments.
    :rtype: [(str, dict)]
    """
    topics = topic if isinstance(topic, list) else [topic]
    normalized = []
    for entry in topics:
        entryArguments = arguments
        if isinstance(entry, dict):
            entryArguments = entry.get('arguments', arguments)
            entry = entry.get('topic', None)
        normalized.append((entry, entryArguments))
    return normalized


async def BasicSubscribe(queue: AbstractQueue, exchange: Union[AbstractExchange, str],
                         topic: Union[List[str], str],
                         arguments: dict = None):
    """
    :param aio_pika.abc.AbstractQueue queue: Declared queue to bind.
    :param aio_pika.abc.AbstractExchange | str exchange: Exchange or exchange name.
    :param str | [str] topic: A topic or a list of topics to subscribe.
    :param dict arguments: Optional binding arguments.
    """
    for entry, entryArguments in NormalizeTopics(topic, arguments):
        await BindQueue(queue, exchange, entry, arguments=entryArguments)


async def BasicUnsubscribe(queue: AbstractQueue, exchange: Union[AbstractExchange, str],
                           topic: Union[List[str], str],
                           arguments: dict = None):
    """
    :param aio_pika.abc.AbstractQueue queue: Declared queue to unbind.
    :param aio_pika.abc.AbstractExchange | str exchange: Exchange or exchange name.
    :param str | [str] topic: A topic or a list of topics to unsubscribe.
    :param dict arguments: Optional binding arguments.
    """
    for entry, entryArguments in NormalizeTopics(topic, arguments):
        await UnbindQueue(queue, exchange, entry, arguments=entryArguments)


async def SafeAcknowledgeMessage(message: aio_pika.abc.AbstractIncomingMessage,
                                 logger=logging.getLogger(__name__)) -> bool:
    """
    Acknowledge a message, tolerating a channel that has already gone away.

    A RobustChannel that was recovered mid-handler invalidates the delivery tag, so ack raises.
    PikaBus guarantees at-least-once delivery, so the correct response is to log and carry on -
    the broker redelivers the message. Crashing here would only mask the real failure.

    :param aio_pika.abc.AbstractIncomingMessage message: Incoming message to acknowledge.
    :param logging logger: Logging object.
    :rtype: bool - True if the acknowledgement reached the broker.
    """
    try:
        await message.ack()
        return True
    except Exception as exception:
        logger.warning(f'Could not acknowledge message - it will be redelivered - '
                       f'{str(type(exception))}: {str(exception)}')
        return False


async def SafeRejectMessage(message: aio_pika.abc.AbstractIncomingMessage,
                            requeue: bool = False,
                            logger=logging.getLogger(__name__)) -> bool:
    """
    Reject a message, tolerating a channel that has already gone away.

    requeue defaults to False so a poison message that also breaks the error handler is dropped
    (or dead-lettered, if the listener queue declares x-dead-letter-exchange) rather than
    redelivered forever, which is what PikaBus 1.x did.

    :param aio_pika.abc.AbstractIncomingMessage message: Incoming message to reject.
    :param bool requeue: Requeue the message.
    :param logging logger: Logging object.
    :rtype: bool - True if the rejection reached the broker.
    """
    try:
        await message.reject(requeue=requeue)
        return True
    except Exception as exception:
        logger.warning(f'Could not reject message - '
                       f'{str(type(exception))}: {str(exception)}')
        return False


class DeprecatedHeaderFrame:
    """
    Backwards-compatibility shim for PikaBus 1.x message handlers.

    1.x handlers read incoming headers as:
        data[DATA_KEY_INCOMING_MESSAGE][DATA_KEY_HEADER_FRAME].headers
    aio-pika has no frame objects, so this exposes just enough of the old pika header frame to
    keep that working for one release, and warns when it is touched.

    Use instead:
        data[DATA_KEY_INCOMING_MESSAGE][DATA_KEY_HEADERS]
    """

    __slots__ = ('_message',)

    def __init__(self, message: aio_pika.abc.AbstractIncomingMessage):
        object.__setattr__(self, '_message', message)

    def _Warn(self, attribute: str):
        warnings.warn(
            f"data['incomingMessage']['headerFrame'].{attribute} is deprecated and will be removed "
            f"in PikaBus 2.1. Read data['incomingMessage']['headers'] for headers, or "
            f"data['incomingMessage']['message'] for the aio_pika incoming message.",
            DeprecationWarning, stacklevel=3)

    @property
    def headers(self):
        self._Warn('headers')
        return object.__getattribute__(self, '_message').headers

    @property
    def delivery_tag(self):
        self._Warn('delivery_tag')
        return object.__getattribute__(self, '_message').delivery_tag

    def __getattr__(self, item: str) -> Any:
        self._Warn(item)
        return getattr(object.__getattribute__(self, '_message'), item)
