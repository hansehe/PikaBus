import pika
from pika import frame
from PikaBus.tools import PikaConstants, PikaTools, PikaOutgoing
from PikaBus.abstractions.AbstractPikaErrorHandler import AbstractPikaErrorHandler


class PikaErrorHandler(AbstractPikaErrorHandler):
    def __init__(self, errorQueue = 'error', maxRetries: int = 5, retryHeader: str = 'PikaBus.ERROR_RETRIES'):
        self._errorQueue = errorQueue
        self._maxRetries = maxRetries
        self._retryHeader = retryHeader

    def HandleFailure(self, data: dict, exception: Exception):
        channel: pika.adapters.blocking_connection.BlockingChannel = data[PikaConstants.DATA_KEY_CHANNEL]
        exchange: str = data[PikaConstants.DATA_KEY_DIRECT_EXCHANGE]
        listenerQueue: str = data[PikaConstants.DATA_KEY_LISTENING_QUEUE]
        incomingMessage = data[PikaConstants.DATA_KEY_INCOMING_MESSAGE]
        headerFrame: frame.Header = incomingMessage[PikaConstants.DATA_KEY_HEADER_FRAME]
        methodFrame: frame.Method = incomingMessage[PikaConstants.DATA_KEY_METHOD_FRAME]
        body: bytes = incomingMessage[PikaConstants.DATA_KEY_BODY]

        updatedHeaders = headerFrame.headers
        retries = self._GetRetries(updatedHeaders) + 1
        updatedHeaders[self._retryHeader] = retries
        destinationQueue = listenerQueue
        if retries > self._maxRetries:
            destinationQueue = self._errorQueue
            PikaTools.CreateDurableQueue(channel, destinationQueue)

        outgoingMessage = PikaOutgoing.GetOutgoingMessage(data, destinationQueue,
                                                          intent=PikaConstants.INTENT_COMMAND,
                                                          headers=updatedHeaders,
                                                          exchange=exchange,
                                                          exception=exception)
        outgoingMessage[PikaConstants.DATA_KEY_BODY] = body
        outgoingMessage[PikaConstants.DATA_KEY_CONTENT_TYPE] = None

        PikaOutgoing.SendOrPublishOutgoingMessage(data, outgoingMessage)
        channel.basic_ack(methodFrame.delivery_tag)

    def _GetRetries(self, headers: dict):
        if self._retryHeader not in headers:
            return 0
        return int(headers[self._retryHeader])


