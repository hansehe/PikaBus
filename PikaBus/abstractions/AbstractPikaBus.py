import abc
import datetime
from typing import Union, List


class AbstractPikaBus(abc.ABC):
    """
    The bus handed to message handlers, and the object returned by PikaBusSetup.CreateBus().

    Changed in 2.0: every method that talks to the broker is a coroutine, and the synchronous
    context manager is replaced by an asynchronous one:

        async with pikaBusSetup.CreateBus() as bus:
            await bus.Publish(payload=payload, topic='myTopic')

    Entering starts a transaction; exiting without an exception commits it. An exception discards the
    buffered outgoing messages without publishing them.

    Not safe for concurrent use: a single bus instance owns one transaction flag and one outbox, so
    sharing one bus across concurrent tasks interleaves their messages. Create a bus per task.
    """

    @property
    @abc.abstractmethod
    def connection(self):
        """
        returns connection.
        :rtype: aio_pika.abc.AbstractRobustConnection
        """
        pass

    @property
    @abc.abstractmethod
    def channel(self):
        """
        returns channel.
        :rtype: aio_pika.abc.AbstractChannel
        """
        pass

    @abc.abstractmethod
    async def Send(self, payload: dict,
                   queue: str = None,
                   headers: dict = None,
                   messageType: str = None,
                   exchange: str = None,
                   mandatory: bool = True):
        """
        :param dict payload: Payload to send
        :param str queue: Destination queue. If None, then it is sent back to the listener queue.
        :param dict headers: Optional headers to add or override
        :param str messageType: Specify message type if necessary.
        :param str exchange: Optional exchange to override with.
        :param bool mandatory: Mandatory delivery to at least one consumer. Added in 2.0.
        """
        pass

    @abc.abstractmethod
    async def Publish(self, payload: dict, topic: str,
                      headers: dict = None,
                      messageType: str = None,
                      exchange: str = None,
                      mandatory: bool = True):
        """
        :param dict payload: Payload to publish
        :param str topic: Topic.
        :param dict headers: Optional headers to add or override
        :param str messageType: Specify message type if necessary.
        :param str exchange: Optional exchange to override with.
        :param bool mandatory: Mandatory delivery to at least one consumer.
        """
        pass

    @abc.abstractmethod
    async def Reply(self, payload: dict,
                    headers: dict = None,
                    messageType: str = None,
                    exchange: str = None):
        """
        :param dict payload: Payload to reply
        :param dict headers: Optional headers to add or override
        :param str messageType: Specify message type if necessary.
        :param str exchange: Optional exchange to override with.
        """
        pass

    @abc.abstractmethod
    async def Defer(self, payload: dict, delay: datetime.timedelta,
                    queue: str = None,
                    headers: dict = None,
                    messageType: str = None,
                    exchange: str = None):
        """
        :param dict payload: Payload to send
        :param datetime.timedelta delay: Delayed relative time from now to process the message.
        :param str queue: Destination queue. If None, then it is sent back to the listener queue.
        :param dict headers: Optional headers to add or override
        :param str messageType: Specify message type if necessary.
        :param str exchange: Optional exchange to override with.
        """
        pass

    @abc.abstractmethod
    async def Subscribe(self, topic: Union[str, List[str]],
                        queue: str = None,
                        exchange: str = None):
        """
        :param str | [str] topic: A topic or a list of topics to subscribe.
        :param str queue: Queue to bind the topic(s). If None, then default listener queue is used.
        :param exchange: Optional exchange to override with.
        """
        pass

    @abc.abstractmethod
    async def Unsubscribe(self, topic: Union[str, List[str]],
                          queue: str = None,
                          exchange: str = None):
        """
        :param str | [str] topic: A topic or a list of topics to unsubscribe.
        :param str queue: Queue to unbind the topic(s). If None, then default listener queue is used.
        :param exchange: Optional exchange to override with.
        """
        pass

    @abc.abstractmethod
    def StartTransaction(self):
        """
        Start a bus transaction. All outgoing messages will be stored until CommitTransaction() is triggered.
        Synchronous - it only sets a flag.
        """
        pass

    @abc.abstractmethod
    async def CommitTransaction(self):
        """
        Commit ongoing bus transaction to send stored outgoing messages.

        This is an in-memory outbox flush, not an AMQP transaction, so it is not atomic. Messages are
        published concurrently; if any fails, PikaBusTransactionError reports which were published and
        which were not. The outbox is always cleared, so a failed commit can never resend later.
        """
        pass

    @abc.abstractmethod
    async def Get(self, queue: str = None, noAck: bool = True):
        """
        Synchronously pull a single message off a queue, or None if it is empty.
        Added in 2.0 to replace direct channel.basic_get() calls.

        :param str queue: Queue to read from. If None, then default listener queue is used.
        :param bool noAck: Acknowledge the message immediately.
        :rtype: aio_pika.abc.AbstractIncomingMessage | None
        """
        pass

    @abc.abstractmethod
    async def Close(self):
        """
        Release the channel and/or connection this bus owns. Idempotent.
        Prefer `async with pikaBusSetup.CreateBus() as bus:` which closes automatically.
        """
        pass
