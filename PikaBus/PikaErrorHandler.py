import pika
from pika import frame
import datetime
import logging
from PikaBus.tools import PikaConstants, PikaTools, PikaOutgoing
from PikaBus.abstractions.AbstractPikaErrorHandler import AbstractPikaErrorHandler
from PikaBus.abstractions.AbstractPikaProperties import AbstractPikaProperties


class PikaErrorHandler(AbstractPikaErrorHandler):
    def __init__(self,
                 errorQueue = 'error',
                 errorQueueArguments: dict = None,
                 maxRetries: int = 5,
                 delay: int = 1,
                 backoff: int = 2,
                 logger=logging.getLogger(__name__)):
        """
        :param str errorQueue: Error queue to dump a failing message.
        :param dict errorQueueArguments: Optional error queue arguments.
        :param int maxRetries: Max retries of a failing message before it is sent to the error queue. -1 is infinite.
        :param int delay: initial delay in seconds between attempts. 0 is no delay.
        :param int backoff: Multiplier applied to delay between attempts. 0 is no back off.
        :param logging logger: Logging object
        """
        self._errorQueue = errorQueue
        self._errorQueueArguments = errorQueueArguments
        self._maxRetries = maxRetries
        self._delay = delay
        self._backoff = backoff
        self._logger = logger

    def HandleFailure(self, data: dict, exception: Exception):
        channel: pika.adapters.blocking_connection.BlockingChannel = data[PikaConstants.DATA_KEY_CHANNEL]
        pikaProperties: AbstractPikaProperties = data[PikaConstants.DATA_KEY_PROPERTY_BUILDER]
        listenerQueue: str = data[PikaConstants.DATA_KEY_LISTENER_QUEUE]
        incomingMessage = data[PikaConstants.DATA_KEY_INCOMING_MESSAGE]
        headerFrame: frame.Header = incomingMessage[PikaConstants.DATA_KEY_HEADER_FRAME]
        methodFrame: frame.Method = incomingMessage[PikaConstants.DATA_KEY_METHOD_FRAME]

        errorRetriesHeaderKey = pikaProperties.errorRetriesHeaderKey
        updatedHeaders: dict = headerFrame.headers
        retries = self._GetRetries(updatedHeaders, errorRetriesHeaderKey) + 1
        updatedHeaders[errorRetriesHeaderKey] = retries
        destinationQueue = listenerQueue

        messageId = updatedHeaders.get(pikaProperties.messageIdHeaderKey, None)
        self._logger.info(f'Handling failed message with id {messageId} for the {retries} time.')

        if retries > self._maxRetries >= 0 or destinationQueue is None:
            destinationQueue = self._errorQueue
            PikaTools.CreateDurableQueue(channel, destinationQueue, arguments=self._errorQueueArguments)
            self._logger.info(f'Moving failed message with id {messageId} '
                              f'to error queue {destinationQueue}')
        elif self._delay > 0:
            deferredTime = self._GetDelayedBackoffTime(retries, pikaProperties, self._delay, self._backoff)
            deferredTimeStr = pikaProperties.DatetimeToString(deferredTime)
            updatedHeaders[pikaProperties.deferredTimeHeaderKey] = deferredTimeStr
            self._logger.info(f'Deferring failed message with id {messageId} to {deferredTimeStr}')

        PikaOutgoing.ResendMessage(data, destinationQueue=destinationQueue, headers=updatedHeaders, exception=exception)
        channel.basic_ack(methodFrame.delivery_tag)

    def _GetRetries(self, headers: dict, errorRetriesHeaderKey: str):
        if errorRetriesHeaderKey not in headers:
            return 0
        return int(headers[errorRetriesHeaderKey])

    def _GetDelayedBackoffTime(self, retry: int, pikaProperties: AbstractPikaProperties, delay: int, backoff: int):
        if backoff > 0:
            delay = retry * delay * backoff
        delayDelta = datetime.timedelta(seconds=delay)
        now = pikaProperties.StringToDatetime(pikaProperties.DatetimeToString())
        return now + delayDelta




