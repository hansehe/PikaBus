import uuid
import datetime
import traceback
import logging

import aio_pika

from PikaBus.tools import PikaConstants
from PikaBus.abstractions.AbstractPikaProperties import AbstractPikaProperties


ISO_TIME_FORMAT = None
LEGACY_TIME_FORMAT = '%m/%d/%Y %H:%M:%S'


def UtcNow() -> datetime.datetime:
    """
    Timezone-aware UTC now, without the deprecated datetime.utcnow().

    :rtype: datetime.datetime
    """
    return datetime.datetime.now(datetime.timezone.utc)


def ParseTimestamp(strTime: str, timeFormat: str = ISO_TIME_FORMAT) -> datetime.datetime:
    """
    Parse a timestamp in a single format. None means ISO 8601.

    :param str strTime: Timestamp string.
    :param str timeFormat: strftime format, or None for ISO 8601.
    :rtype: datetime.datetime
    """
    if timeFormat is ISO_TIME_FORMAT:
        # fromisoformat handles the full ISO 8601 grammar on Python 3.11+, including a 'Z' suffix
        # and offsets written with or without a colon.
        return datetime.datetime.fromisoformat(strTime)
    return datetime.datetime.strptime(strTime, timeFormat)


class PikaProperties(AbstractPikaProperties):
    def __init__(self,
                 headerPrefix: str = 'PikaBus',
                 timeFormat: str = None,
                 deliveryMode: int = 2,
                 logger=logging.getLogger(__name__)):
        """
        :param str headerPrefix: Prefixed header part of all headers.
        :param str timeFormat: Optional strftime format for header timestamps. Leave as None to use
            ISO 8601, which is the default since 2.0 - timezone-aware and microsecond precise, e.g.
            '2026-08-07T16:32:19.123456+00:00'. PikaBus 1.x used '%m/%d/%Y %H:%M:%S', an ambiguous
            US-style format with no timezone and only second resolution, which put a one second floor
            under Defer() and every error-handler retry backoff.
            This only controls what is *written*. Reading accepts both formats regardless, so a
            rolling 1.x to 2.0 upgrade does not send in-flight messages to the error queue.
        :param: int deliveryMode: Delivery mode. 1 == messages stored in memory. 2 == messages persisted on disk.
        :param logging logger: Logging object
        """
        self._headerPrefix = headerPrefix
        self._timeFormat = timeFormat
        self._deliveryMode = deliveryMode
        self._logger = logger
        self._warnedFallbackFormats = set()

    def GetPikaProperties(self, data: dict, outgoingMessage: dict) -> aio_pika.Message:
        self._SetHeaders(data, outgoingMessage)
        return self._CreateMessage(outgoingMessage)

    def DatetimeToString(self,
                         time: datetime.datetime = None):
        if time is None:
            time = UtcNow()
        if time.tzinfo is None:
            time = time.replace(tzinfo=datetime.timezone.utc)
        if self._timeFormat is None:
            return time.isoformat()
        return time.strftime(self._timeFormat)

    def StringToDatetime(self, strTime: str):
        """
        Parse a header timestamp, falling back to the other known format if the configured one fails.

        The fallback is what makes a rolling upgrade safe. Without it, a 2.0 consumer handed a 1.x
        timestamp raises, the pipeline treats that as a message failure, and the whole queue drains
        into the error queue mid-deployment. The fallback is symmetric, so a service temporarily
        pinned to the legacy format with timeFormat= can still read ISO messages from an
        already-upgraded publisher.
        """
        time = None
        try:
            time = ParseTimestamp(strTime, self._timeFormat)
        except (ValueError, TypeError) as primaryError:
            for fallbackFormat in self._GetFallbackTimeFormats():
                try:
                    time = ParseTimestamp(strTime, fallbackFormat)
                except (ValueError, TypeError):
                    continue
                self._WarnAboutFallbackOnce(fallbackFormat)
                break
            if time is None:
                raise ValueError(
                    f'Could not parse timestamp {strTime!r} as '
                    f'{self._DescribeTimeFormat(self._timeFormat)} or as '
                    f'{" or ".join(self._DescribeTimeFormat(f) for f in self._GetFallbackTimeFormats())}.'
                ) from primaryError
        if time.tzinfo is None:
            # The legacy format carries no offset. Interpret it as UTC, which is what PikaBus has
            # always written, so every datetime the pipeline compares is aware and comparisons
            # cannot raise TypeError on mixing aware and naive values.
            time = time.replace(tzinfo=datetime.timezone.utc)
        return time

    def _GetFallbackTimeFormats(self):
        if self._timeFormat is ISO_TIME_FORMAT:
            return [LEGACY_TIME_FORMAT]
        if self._timeFormat == LEGACY_TIME_FORMAT:
            return [ISO_TIME_FORMAT]
        # A fully custom format still gets both known PikaBus formats as fallbacks.
        return [ISO_TIME_FORMAT, LEGACY_TIME_FORMAT]

    @staticmethod
    def _DescribeTimeFormat(timeFormat: str):
        return 'ISO 8601' if timeFormat is ISO_TIME_FORMAT else repr(timeFormat)

    def _WarnAboutFallbackOnce(self, fallbackFormat: str):
        # Once per format per instance. Worth surfacing rather than silently absorbing: it means a
        # process on the other timestamp format is still publishing, i.e. the rollout is not finished.
        if fallbackFormat in self._warnedFallbackFormats:
            return
        self._warnedFallbackFormats.add(fallbackFormat)
        self._logger.warning(
            f'Parsed an incoming timestamp as {self._DescribeTimeFormat(fallbackFormat)} after '
            f'{self._DescribeTimeFormat(self._timeFormat)} failed. Another PikaBus version is still '
            f'publishing to this queue. This message will not repeat for this format.')

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
    def messageTypeHeaderKey(self):
        return f'{self._headerPrefix}.{PikaConstants.HEADER_KEY_MESSAGE_TYPE}'

    @property
    def contentTypeHeaderKey(self):
        return f'{self._headerPrefix}.{PikaConstants.HEADER_KEY_CONTENT_TYPE}'

    @property
    def contentEncodingHeaderKey(self):
        return f'{self._headerPrefix}.{PikaConstants.HEADER_KEY_CONTENT_ENCODING}'

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
            headers.setdefault(self.messageTypeHeaderKey, messageType)

    def _TrySetContentType(self, outgoingMessage: dict):
        headers: dict = outgoingMessage[PikaConstants.DATA_KEY_HEADERS]
        contentType = outgoingMessage.get(PikaConstants.DATA_KEY_CONTENT_TYPE, None)
        contentEncoding = outgoingMessage.get(PikaConstants.DATA_KEY_CONTENT_ENCODING, None)
        if contentType is not None:
            headers.setdefault(self.contentTypeHeaderKey, contentType)
        if contentEncoding is not None:
            headers.setdefault(self.contentEncodingHeaderKey, contentEncoding)

    def _TrySetCorrelationId(self, data: dict, outgoingMessage: dict):
        headers: dict = outgoingMessage[PikaConstants.DATA_KEY_HEADERS]
        correlationIdKey = self.correlationIdHeaderKey
        correlationId = str(uuid.uuid1())
        if PikaConstants.DATA_KEY_INCOMING_MESSAGE in data:
            incomingMessageHeaders: dict = data[PikaConstants.DATA_KEY_INCOMING_MESSAGE].get(
                PikaConstants.DATA_KEY_HEADERS, None) or {}
            if correlationIdKey in incomingMessageHeaders:
                correlationId = incomingMessageHeaders[correlationIdKey]
        headers.setdefault(correlationIdKey, correlationId)

    def _TrySetException(self, data: dict, outgoingMessage: dict):
        headers: dict = outgoingMessage[PikaConstants.DATA_KEY_HEADERS]
        exception = outgoingMessage.get(PikaConstants.DATA_KEY_EXCEPTION, None)
        if exception is not None:
            errorDetails = ''.join(traceback.format_exception(type(exception), exception, exception.__traceback__))
            headers[self.errorDetailsHeaderKey] = errorDetails
            if data[PikaConstants.DATA_KEY_LISTENER_QUEUE] is not None:
                headers.setdefault(self.sourceQueueHeaderKey, data[PikaConstants.DATA_KEY_LISTENER_QUEUE])

    def _SetHeaders(self, data: dict, outgoingMessage: dict):
        self._TrySetDefaultHeaders(data, outgoingMessage)
        self._TrySetMessageType(outgoingMessage)
        self._TrySetContentType(outgoingMessage)
        self._TrySetCorrelationId(data, outgoingMessage)
        self._TrySetException(data, outgoingMessage)

    def _CreateMessage(self, outgoingMessage: dict) -> aio_pika.Message:
        headers: dict = outgoingMessage[PikaConstants.DATA_KEY_HEADERS]
        # StringToDatetime always returns an aware datetime; normalise to UTC in case a caller supplied
        # a TimeSent header in another offset. PikaBus 1.x instead ran the naive value through
        # time.mktime(), which reads it as *local* time, so every published AMQP timestamp was off by
        # the machine's UTC offset - and by a different amount either side of a DST change.
        timestamp = self.StringToDatetime(
            headers.get(self.timeSentHeaderKey, self.DatetimeToString())
        ).astimezone(datetime.timezone.utc)
        return aio_pika.Message(
            outgoingMessage[PikaConstants.DATA_KEY_BODY],
            headers=headers,
            content_type=headers.get(self.contentTypeHeaderKey, None),
            content_encoding=headers.get(self.contentEncodingHeaderKey, None),
            delivery_mode=headers.get('delivery_mode', self._deliveryMode),
            priority=headers.get('priority', None),
            correlation_id=headers.get(self.correlationIdHeaderKey, None),
            reply_to=headers.get(self.replyToAddressHeaderKey, None),
            expiration=headers.get('expiration', None),
            message_id=headers.get(self.messageIdHeaderKey, None),
            timestamp=timestamp,
            type=headers.get(self.messageTypeHeaderKey, None),
            user_id=headers.get('user_id', None),
            app_id=headers.get('app_id', None))
        # Note: pika's BasicProperties had a cluster_id field which aio_pika.Message does not.
        # It is a deprecated AMQP field that RabbitMQ ignores, so it is simply dropped.
