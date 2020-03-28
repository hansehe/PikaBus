import uuid
import datetime
import traceback
import pika
import logging
from PikaBus.tools import PikaConstants
from PikaBus.abstractions.AbstractPikaProperties import AbstractPikaProperties


class PikaProperties(AbstractPikaProperties):
    def __init__(self,
                 headerPrefix = 'PikaBus',
                 timeFormat = '%m/%d/%Y %H:%M:%S',
                 logger=logging.getLogger(__name__)):
        """
        :param str headerPrefix: Prefixed header part of all headers.
        :param str timeFormat: Timeformat of header timestamps.
        :param logging logger: Logging object
        """
        self._headerPrefix = headerPrefix
        self._timeFormat = timeFormat
        self._logger = logger

    def GetPikaProperties(self, data: dict, outgoingMessage: dict):
        self._TrySetDefaultHeaders(data, outgoingMessage)
        self._TrySetMessageType(outgoingMessage)
        self._TrySetContentType(outgoingMessage)
        self._TrySetCorrelationId(data, outgoingMessage)
        self._TrySetException(data, outgoingMessage)

        headers: dict = outgoingMessage[PikaConstants.DATA_KEY_HEADERS]
        properties = pika.spec.BasicProperties(headers=headers)
        return properties

    def DatetimeToString(self,
                         time: datetime.datetime = None):
        if time is None:
            time = datetime.datetime.utcnow()
        return time.strftime(self._timeFormat)

    def StringToDatetime(self, strTime: str):
        return datetime.datetime.strptime(strTime, self._timeFormat)

    @property
    def messageIdHeaderKey(self):
        return f'{self._headerPrefix}.{PikaConstants.HEADER_KEY_MESSAGE_ID}'

    @property
    def correlationIdHeaderKey(self):
        return f'{self._headerPrefix}.{PikaConstants.HEADER_KEY_CORRELATION_ID}'

    @property
    def timeSentHeaderKey(self):
        return f'{self._headerPrefix}.{PikaConstants.HEADER_KEY_TIME_SENT}'

    @property
    def replyToAddressHeaderKey(self):
        return f'{self._headerPrefix}.{PikaConstants.HEADER_KEY_REPLY_TO_ADDRESS}'

    @property
    def originatingAddressHeaderKey(self):
        return f'{self._headerPrefix}.{PikaConstants.HEADER_KEY_ORIGINATING_ADDRESS}'

    @property
    def intentHeaderKey(self):
        return f'{self._headerPrefix}.{PikaConstants.HEADER_KEY_INTENT}'

    @property
    def messsageTypeHeaderKey(self):
        return f'{self._headerPrefix}.{PikaConstants.HEADER_KEY_MESSAGE_TYPE}'

    @property
    def contentTypeHeaderKey(self):
        return f'{self._headerPrefix}.{PikaConstants.HEADER_KEY_CONTENT_TYPE}'

    @property
    def errorDetailsHeaderKey(self):
        return f'{self._headerPrefix}.{PikaConstants.HEADER_KEY_ERROR_DETAILS}'

    @property
    def sourceQueueHeaderKey(self):
        return f'{self._headerPrefix}.{PikaConstants.HEADER_KEY_SOURCE_QUEUE}'

    @property
    def errorRetriesHeaderKey(self):
        return f'{self._headerPrefix}.{PikaConstants.HEADER_KEY_ERROR_RETRIES}'

    @property
    def deferredTimeHeaderKey(self):
        return f'{self._headerPrefix}.{PikaConstants.HEADER_KEY_DEFERRED_TIME}'

    def _TrySetDefaultHeaders(self, data: dict, outgoingMessage: dict):
        headers: dict = outgoingMessage[PikaConstants.DATA_KEY_HEADERS]
        headers.setdefault(self.messageIdHeaderKey, str(uuid.uuid1()))
        headers.setdefault(self.timeSentHeaderKey, self.DatetimeToString())
        if data[PikaConstants.DATA_KEY_LISTENER_QUEUE] is not None:
            headers.setdefault(self.replyToAddressHeaderKey, data[PikaConstants.DATA_KEY_LISTENER_QUEUE])
            headers.setdefault(self.originatingAddressHeaderKey, data[PikaConstants.DATA_KEY_LISTENER_QUEUE])
        headers.setdefault(self.intentHeaderKey, outgoingMessage[PikaConstants.DATA_KEY_INTENT])

    def _TrySetMessageType(self, outgoingMessage: dict):
        headers: dict = outgoingMessage[PikaConstants.DATA_KEY_HEADERS]
        messageType = outgoingMessage[PikaConstants.DATA_KEY_MESSAGE_TYPE]
        if messageType is not None:
            headers.setdefault(self.messsageTypeHeaderKey, messageType)

    def _TrySetContentType(self, outgoingMessage: dict):
        headers: dict = outgoingMessage[PikaConstants.DATA_KEY_HEADERS]
        contentType = outgoingMessage.get(PikaConstants.DATA_KEY_CONTENT_TYPE, None)
        if contentType is not None:
            headers.setdefault(self.contentTypeHeaderKey, outgoingMessage[PikaConstants.DATA_KEY_CONTENT_TYPE])

    def _TrySetCorrelationId(self, data: dict, outgoingMessage: dict):
        headers: dict = outgoingMessage[PikaConstants.DATA_KEY_HEADERS]
        correlationIdKey = self.correlationIdHeaderKey
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
            headers.setdefault(self.errorDetailsHeaderKey, errorDetails)
            if data[PikaConstants.DATA_KEY_LISTENER_QUEUE] is not None:
                headers.setdefault(self.sourceQueueHeaderKey, data[PikaConstants.DATA_KEY_LISTENER_QUEUE])
