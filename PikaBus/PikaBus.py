import pika
import pika.exceptions
from PikaBus.tools import PikaTools, PikaConstants, PikaOutgoing
from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus


class PikaBus(AbstractPikaBus):
    def __init__(self, data: dict, closeConnectionOnDelete = False):
        self._data = data
        self._connection: pika.BlockingConnection = data[PikaConstants.DATA_KEY_CONNECTION]
        self._channel: pika.adapters.blocking_connection.BlockingChannel = data[PikaConstants.DATA_KEY_CHANNEL]
        self._directExchange: str = data[PikaConstants.DATA_KEY_DIRECT_EXCHANGE]
        self._topicExchange: str = data[PikaConstants.DATA_KEY_TOPIC_EXCHANGE]
        self._listenerQueue: str = data[PikaConstants.DATA_KEY_LISTENING_QUEUE]
        self._transaction: bool = False
        self._closeConnectionOnDelete = closeConnectionOnDelete

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
                PikaTools.AssertDurableQueueExists(self._connection, topicOrQueue)
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
