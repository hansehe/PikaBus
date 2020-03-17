import datetime
import logging
import pika
import pika.exceptions
from PikaBus.tools import PikaTools, PikaConstants, PikaOutgoing
from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus
from PikaBus.abstractions.AbstractPikaProperties import AbstractPikaProperties


class PikaBus(AbstractPikaBus):
    def __init__(self, data: dict,
                 closeConnectionOnDelete: bool = False,
                 logger=logging.getLogger(__name__)):
        """
        :param dict data: General data holder
        :param bool closeConnectionOnDelete: True if the connection stored in 'data' should be closed on instance deletion.
        :param logging logger: Logging object
        """
        self._data = data
        self._connection: pika.BlockingConnection = data[PikaConstants.DATA_KEY_CONNECTION]
        self._channel: pika.adapters.blocking_connection.BlockingChannel = data[PikaConstants.DATA_KEY_CHANNEL]
        self._pikaProperties: AbstractPikaProperties = data[PikaConstants.DATA_KEY_PROPERTY_BUILDER]
        self._directExchange: str = data[PikaConstants.DATA_KEY_DIRECT_EXCHANGE]
        self._topicExchange: str = data[PikaConstants.DATA_KEY_TOPIC_EXCHANGE]
        self._listenerQueue: str = data[PikaConstants.DATA_KEY_LISTENING_QUEUE]
        self._transaction: bool = False
        self._closeConnectionOnDelete = closeConnectionOnDelete
        self._logger = logger

    def __del__(self):
        if self._closeConnectionOnDelete:
            PikaTools.SafeCloseConnection(self._connection)

    def Send(self, payload: dict, queue: str = None, headers: dict = {}, messageType: str = None, exchange: str = None):
        if exchange is None:
            exchange = self._directExchange
        if queue is None:
            queue = self._listenerQueue
        self._SendOrPublish(PikaConstants.INTENT_COMMAND, payload, queue, exchange,
                            headers=headers,
                            messageType=messageType)

    def Publish(self, payload: dict, topic: str, headers: dict = {}, messageType: str = None, exchange: str = None):
        if exchange is None:
            exchange = self._topicExchange
        self._SendOrPublish(PikaConstants.INTENT_EVENT, payload, topic, exchange,
                            headers=headers,
                            messageType=messageType)

    def Reply(self, payload: dict, headers: dict = {}, messageType: str = None, exchange: str = None):
        replyToAddressHeaderKey = self._pikaProperties.replyToAddressHeaderKey
        if PikaConstants.DATA_KEY_INCOMING_MESSAGE not in self._data:
            msg = 'Cannot perform a perform a reply outside of a message transaction.'
            self._logger.exception(msg)
            raise Exception(msg)
        incomingMessageHeaders: dict = self._data[PikaConstants.DATA_KEY_INCOMING_MESSAGE][PikaConstants.DATA_KEY_HEADER_FRAME].headers
        if replyToAddressHeaderKey not in incomingMessageHeaders:
            msg = f"The reply address header key {replyToAddressHeaderKey} is not present in incoming message headers."
            self._logger.exception(msg)
            raise Exception(msg)
        replyToAddress = incomingMessageHeaders[replyToAddressHeaderKey]
        self.Send(payload, queue=replyToAddress, headers=headers, messageType=messageType, exchange=exchange)

    def Defer(self, payload: dict, delay: datetime.timedelta, queue: str = None, headers: dict = {}, messageType: str = None, exchange: str = None):
        now = self._pikaProperties.StringToDatetime(self._pikaProperties.DatetimeToString())
        deferredTime = now + delay
        headers.setdefault(self._pikaProperties.deferredTimeHeaderKey, self._pikaProperties.DatetimeToString(deferredTime))
        self.Send(payload, queue=queue, headers=headers, messageType=messageType, exchange=exchange)

    def Subscribe(self, topic: str, exchange: str = None):
        if exchange is None:
            exchange = self._topicExchange
        PikaTools.CreateExchange(self._channel, exchange, exchangeType='topic')
        PikaTools.BindQueue(self._channel, self._listenerQueue, exchange, topic)

    def StartTransaction(self):
        self._data.setdefault(PikaConstants.DATA_KEY_OUTGOING_MESSAGES, [])
        self._transaction = True

    def CommitTransaction(self):
        PikaOutgoing.SendOrPublishOutgoingMessages(self._data)
        self._transaction = False

    def _SendOrPublish(self, intent: str, payload: dict, topicOrQueue: str, exchange: str, headers: dict = {}, messageType: str = None):
        if self._transaction:
            if intent == PikaConstants.INTENT_COMMAND:
                PikaTools.AssertDurableQueueExists(self._connection, topicOrQueue, logger=self._logger)
            PikaOutgoing.AppendOutgoingMessage(self._data, payload, topicOrQueue,
                                               intent=intent,
                                               headers=headers,
                                               messageType=messageType,
                                               exchange=exchange)
        else:
            outgoingMessage = PikaOutgoing.GetOutgoingMessage(self._data, topicOrQueue,
                                                              payload=payload,
                                                              intent=intent,
                                                              headers=headers,
                                                              messageType=messageType,
                                                              exchange=exchange)
            PikaOutgoing.SendOrPublishOutgoingMessage(self._data, outgoingMessage)