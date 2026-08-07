import datetime
import logging
import warnings
from typing import Union, List

import aio_pika

from PikaBus.tools import PikaTools, PikaConstants, PikaOutgoing
from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus
from PikaBus.abstractions.AbstractPikaProperties import AbstractPikaProperties


class PikaBus(AbstractPikaBus):
    def __init__(self, data: dict,
                 closeChannelOnExit: bool = False,
                 closeConnectionOnExit: bool = False,
                 logger=logging.getLogger(__name__)):
        """
        :param dict data: General data holder
        :param bool closeChannelOnExit: True if the channel stored in 'data' should be closed when the bus is closed.
        :param bool closeConnectionOnExit: True if the connection stored in 'data' should be closed when the bus is closed.
        :param logging logger: Logging object
        """
        self._data = data
        self._connection: aio_pika.abc.AbstractRobustConnection = data[PikaConstants.DATA_KEY_CONNECTION]
        self._channel: aio_pika.abc.AbstractChannel = data[PikaConstants.DATA_KEY_CHANNEL]
        self._pikaProperties: AbstractPikaProperties = data[PikaConstants.DATA_KEY_PROPERTY_BUILDER]
        self._listenerQueue: str = data[PikaConstants.DATA_KEY_LISTENER_QUEUE]
        self._directExchange: str = data[PikaConstants.DATA_KEY_DIRECT_EXCHANGE]
        self._topicExchange: str = data[PikaConstants.DATA_KEY_TOPIC_EXCHANGE]
        self._transaction: bool = False
        self._closeChannelOnExit = closeChannelOnExit
        self._closeConnectionOnExit = closeConnectionOnExit
        self._closed = False
        self._logger = logger

    def __del__(self):
        # Closing is asynchronous in 2.0 and there is no loop to await on during garbage collection,
        # so this only warns. This mirrors what asyncio itself does for unclosed transports.
        if self._closed:
            return
        if not (self._closeChannelOnExit or self._closeConnectionOnExit):
            return
        if self._channel is not None and not self._channel.is_closed:
            warnings.warn(f'Unclosed PikaBus {self!r} - '
                          f'use "async with pikaBusSetup.CreateBus() as bus:" or await bus.Close().',
                          ResourceWarning, source=self)

    def __enter__(self):
        raise TypeError('PikaBus is asynchronous in 2.0. '
                        'Use "async with pikaBusSetup.CreateBus() as bus:" instead of "with".')

    def __exit__(self, excType, value, traceback):
        raise TypeError('PikaBus is asynchronous in 2.0. '
                        'Use "async with pikaBusSetup.CreateBus() as bus:" instead of "with".')

    async def __aenter__(self):
        self.StartTransaction()
        return self

    async def __aexit__(self, excType, value, traceback):
        try:
            if not isinstance(value, BaseException):
                await self.CommitTransaction()
            elif self._data.get(PikaConstants.DATA_KEY_OUTGOING_MESSAGES, None):
                # Deliberate: an exception discards the outbox instead of publishing a partial batch.
                self._logger.debug(
                    f'Discarding {len(self._data[PikaConstants.DATA_KEY_OUTGOING_MESSAGES])} '
                    f'outgoing message(s) - transaction exited with '
                    f'{str(type(value))}: {str(value)}')
                self._data[PikaConstants.DATA_KEY_OUTGOING_MESSAGES] = []
                self._transaction = False
        finally:
            await self.Close()

    @property
    def connection(self):
        return self._connection

    @property
    def channel(self):
        return self._channel

    async def Close(self):
        if self._closed:
            return
        self._closed = True
        if self._closeChannelOnExit:
            await PikaTools.SafeCloseChannel(self._channel)
        if self._closeConnectionOnExit:
            await PikaTools.SafeCloseConnection(self._connection)

    async def Send(self, payload: dict,
                   queue: str = None,
                   headers: dict = None,
                   messageType: str = None,
                   exchange: str = None,
                   mandatory: bool = True):
        queue = self._SafeGetQueue(queue)
        if exchange is None:
            exchange = self._directExchange
        await self._SendOrPublish(PikaConstants.INTENT_COMMAND, payload, queue, exchange,
                                  headers=headers,
                                  messageType=messageType,
                                  mandatory=mandatory)

    async def Publish(self, payload: dict, topic: str,
                      headers: dict = None,
                      messageType: str = None,
                      exchange: str = None,
                      mandatory: bool = True):
        if exchange is None:
            exchange = self._topicExchange
        await self._SendOrPublish(PikaConstants.INTENT_EVENT, payload, topic, exchange,
                                  headers=headers,
                                  messageType=messageType,
                                  mandatory=mandatory)

    async def Reply(self, payload: dict,
                    headers: dict = None,
                    messageType: str = None,
                    exchange: str = None):
        replyToAddressHeaderKey = self._pikaProperties.replyToAddressHeaderKey
        if PikaConstants.DATA_KEY_INCOMING_MESSAGE not in self._data:
            msg = 'Cannot perform a reply outside of a message transaction.'
            self._logger.error(msg)
            raise Exception(msg)
        incomingMessageHeaders: dict = self._data[PikaConstants.DATA_KEY_INCOMING_MESSAGE].get(
            PikaConstants.DATA_KEY_HEADERS, None) or {}
        if replyToAddressHeaderKey not in incomingMessageHeaders:
            msg = f"The reply address header key {replyToAddressHeaderKey} is not present in incoming message headers."
            self._logger.error(msg)
            raise Exception(msg)
        replyToAddress = incomingMessageHeaders[replyToAddressHeaderKey]
        await self.Send(payload, queue=replyToAddress, headers=headers, messageType=messageType, exchange=exchange)

    async def Defer(self, payload: dict, delay: datetime.timedelta,
                    queue: str = None,
                    headers: dict = None,
                    messageType: str = None,
                    exchange: str = None):
        if headers is None:
            headers = {}
        now = self._pikaProperties.StringToDatetime(self._pikaProperties.DatetimeToString())
        deferredTime = now + delay
        headers.setdefault(self._pikaProperties.deferredTimeHeaderKey,
                           self._pikaProperties.DatetimeToString(deferredTime))
        await self.Send(payload, queue=queue, headers=headers, messageType=messageType, exchange=exchange)

    async def Subscribe(self, topic: Union[str, List[str]],
                        queue: str = None,
                        exchange: str = None):
        queue = self._SafeGetQueue(queue)
        if exchange is None:
            exchange = self._topicExchange
        declaredQueue = await self._channel.get_queue(queue, ensure=False)
        await PikaTools.BasicSubscribe(declaredQueue, exchange, topic)

    async def Unsubscribe(self, topic: Union[str, List[str]],
                          queue: str = None,
                          exchange: str = None):
        queue = self._SafeGetQueue(queue)
        if exchange is None:
            exchange = self._topicExchange
        declaredQueue = await self._channel.get_queue(queue, ensure=False)
        await PikaTools.BasicUnsubscribe(declaredQueue, exchange, topic)

    async def Get(self, queue: str = None, noAck: bool = True):
        queue = self._SafeGetQueue(queue)
        declaredQueue = await self._channel.get_queue(queue, ensure=False)
        return await declaredQueue.get(no_ack=noAck, fail=False)

    def StartTransaction(self):
        self._data.setdefault(PikaConstants.DATA_KEY_OUTGOING_MESSAGES, [])
        self._transaction = True

    async def CommitTransaction(self):
        try:
            await PikaOutgoing.SendOrPublishOutgoingMessages(self._data)
        finally:
            # Always cleared, even on failure. PikaBus 1.x left the list populated when a publish
            # raised, so a later commit resent the messages that had already gone out.
            self._data[PikaConstants.DATA_KEY_OUTGOING_MESSAGES] = []
            self._transaction = False

    def _SafeGetQueue(self, queue: str):
        if queue is None:
            if self._listenerQueue is None:
                msg = f'Cannot use local listener queue when it is not defined!'
                self._logger.error(msg)
                raise Exception(msg)
            queue = self._listenerQueue
        return queue

    async def _SendOrPublish(self, intent: str, payload: dict, topicOrQueue: str, exchange: str,
                             headers: dict = None,
                             messageType: str = None,
                             mandatory: bool = True):
        if self._transaction:
            # PikaBus 1.x did a passive queue_declare on a throwaway channel here to fail early on a
            # missing destination - three extra round trips per send. Publisher confirms with
            # mandatory delivery report an unroutable destination on the channel we already have,
            # so the check is redundant. Trade-off: the failure now surfaces at CommitTransaction()
            # rather than at Send().
            PikaOutgoing.AppendOutgoingMessage(self._data, payload, topicOrQueue,
                                               intent=intent,
                                               headers=headers,
                                               messageType=messageType,
                                               exchange=exchange,
                                               mandatory=mandatory)
        else:
            outgoingMessage = PikaOutgoing.GetOutgoingMessage(self._data, topicOrQueue,
                                                              payload=payload,
                                                              intent=intent,
                                                              headers=headers,
                                                              messageType=messageType,
                                                              exchange=exchange,
                                                              mandatory=mandatory)
            await PikaOutgoing.SendOrPublishOutgoingMessage(self._data, outgoingMessage)
