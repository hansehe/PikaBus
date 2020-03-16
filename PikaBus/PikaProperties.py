import uuid
import datetime
import traceback
import pika
from PikaBus.tools import PikaConstants
from PikaBus.abstractions.AbstractPikaProperties import AbstractPikaProperties


class PikaProperties(AbstractPikaProperties):
    def __init__(self, headerPrefix = 'PikaBus', timeFormat = '{0:%m/%d/%Y %H:%M:%S}'):
        self._headerPrefix = headerPrefix
        self._timeFormat = timeFormat

    def GetPikaProperties(self, data: dict, outgoingMessage: dict):
        self._TrySetDefaultHeaders(data, outgoingMessage)
        self._TrySetMessageType(outgoingMessage)
        self._TrySetContentType(outgoingMessage)
        self._TrySetCorrelationId(data, outgoingMessage)
        self._TrySetException(data, outgoingMessage)

        headers: dict = outgoingMessage[PikaConstants.DATA_KEY_HEADERS]
        properties = pika.spec.BasicProperties(headers=headers)
        return properties

    def _TrySetDefaultHeaders(self, data: dict, outgoingMessage: dict):
        headers: dict = outgoingMessage[PikaConstants.DATA_KEY_HEADERS]
        headers.setdefault(f'{self._headerPrefix}.{PikaConstants.HEADER_KEY_MESSAGE_ID}', str(uuid.uuid1()))
        headers.setdefault(f'{self._headerPrefix}.{PikaConstants.HEADER_KEY_TIME_SENT}', self._timeFormat.format(datetime.datetime.now()))
        headers.setdefault(f'{self._headerPrefix}.{PikaConstants.HEADER_KEY_REPLY_TO_ADDRESS}', data[PikaConstants.DATA_KEY_LISTENING_QUEUE])
        headers.setdefault(f'{self._headerPrefix}.{PikaConstants.HEADER_KEY_ORIGINATING_ADDRESS}', data[PikaConstants.DATA_KEY_LISTENING_QUEUE])
        headers.setdefault(f'{self._headerPrefix}.{PikaConstants.HEADER_KEY_INTENT}', outgoingMessage[PikaConstants.DATA_KEY_INTENT])

    def _TrySetMessageType(self, outgoingMessage: dict):
        headers: dict = outgoingMessage[PikaConstants.DATA_KEY_HEADERS]
        messageType = outgoingMessage[PikaConstants.DATA_KEY_MESSAGE_TYPE]
        if messageType is not None:
            headers.setdefault(f'{self._headerPrefix}.{PikaConstants.DATA_KEY_MESSAGE_TYPE}', messageType)

    def _TrySetContentType(self, outgoingMessage: dict):
        headers: dict = outgoingMessage[PikaConstants.DATA_KEY_HEADERS]
        contentType = outgoingMessage.get(PikaConstants.DATA_KEY_CONTENT_TYPE, None)
        if contentType is not None:
            headers.setdefault(f'{self._headerPrefix}.{PikaConstants.HEADER_KEY_CONTENT_TYPE}', outgoingMessage[PikaConstants.DATA_KEY_CONTENT_TYPE])

    def _TrySetCorrelationId(self, data: dict, outgoingMessage: dict):
        headers: dict = outgoingMessage[PikaConstants.DATA_KEY_HEADERS]
        correlationIdKey = f'{self._headerPrefix}.{PikaConstants.HEADER_KEY_CORRELATION_ID}'
        correlationId = str(uuid.uuid1())
        if PikaConstants.DATA_KEY_INCOMING_MESSAGE in data:
            incomingMessageHeaders: dict = data[PikaConstants.DATA_KEY_INCOMING_MESSAGE][PikaConstants.DATA_KEY_HEADER_FRAME].headers
            if correlationIdKey in incomingMessageHeaders:
                correlationId = incomingMessageHeaders[correlationIdKey]
        headers.setdefault(correlationIdKey, correlationId)

    def _TrySetException(self, data: dict, outgoingMessage: dict):
        headers: dict = outgoingMessage[PikaConstants.DATA_KEY_HEADERS]
        exception = outgoingMessage.get(PikaConstants.DATA_KEY_EXCEPTION, None)
        if exception is not None:
            errorDetails = ''.join(traceback.format_exception(type(exception), exception, exception.__traceback__))
            headers.setdefault(f'{self._headerPrefix}.{PikaConstants.HEADER_KEY_ERROR_DETAILS}', errorDetails)
            headers.setdefault(f'{self._headerPrefix}.{PikaConstants.HEADER_KEY_SOURCE_QUEUE}', data[PikaConstants.DATA_KEY_LISTENING_QUEUE])