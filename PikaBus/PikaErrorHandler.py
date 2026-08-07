import datetime
import logging

import aio_pika

from PikaBus.tools import PikaConstants, PikaTools, PikaOutgoing
from PikaBus.abstractions.AbstractPikaErrorHandler import AbstractPikaErrorHandler
from PikaBus.abstractions.AbstractPikaProperties import AbstractPikaProperties


class PikaErrorHandler(AbstractPikaErrorHandler):
    def __init__(self,
                 errorQueue='error',
                 errorQueueSettings: dict = None,
                 maxRetries: int = 5,
                 delay: int = 1,
                 backoff: int = 2,
                 logger=logging.getLogger(__name__)):
        """
        :param str errorQueue: Error queue to dump a failing message.
        :param dict errorQueueSettings: Optional error queue settings. Empty by default since 2.0 -
            the 1.x default of {'arguments': {'ha-mode': 'all'}} never had any effect, because
            classic queue mirroring was configured through policies, not queue arguments.
            For real redundancy use {'arguments': {'x-queue-type': 'quorum'}} on a NEW queue.
        :param int maxRetries: Max retries of a failing message before it is sent to the error queue. -1 is infinite.
        :param int delay: initial delay in seconds between attempts. 0 is no delay.
        :param int backoff: Multiplier applied to delay between attempts. 0 is no back off.
            Note the ramp is linear (retry * delay * backoff), unchanged from 1.x.
        :param logging logger: Logging object
        """
        if errorQueueSettings is None:
            errorQueueSettings = {}
        self._errorQueue = errorQueue
        self._errorQueueSettings = errorQueueSettings
        self._maxRetries = maxRetries
        self._delay = delay
        self._backoff = backoff
        self._logger = logger

    async def HandleFailure(self, data: dict, exception: Exception):
        channel: aio_pika.abc.AbstractChannel = data[PikaConstants.DATA_KEY_CHANNEL]
        connection: aio_pika.abc.AbstractRobustConnection = data[PikaConstants.DATA_KEY_CONNECTION]
        pikaProperties: AbstractPikaProperties = data[PikaConstants.DATA_KEY_PROPERTY_BUILDER]
        listenerQueue: str = data[PikaConstants.DATA_KEY_LISTENER_QUEUE]
        incomingMessage = data[PikaConstants.DATA_KEY_INCOMING_MESSAGE]
        message: aio_pika.abc.AbstractIncomingMessage = incomingMessage[PikaConstants.DATA_KEY_MESSAGE]

        if channel.is_closed or connection.is_closed:
            # Nothing can be published or acknowledged on a dead channel, and the broker requeues
            # every unacked delivery when it closes. Log once and let redelivery handle it, rather
            # than raising a second, misleading exception on top of the original failure.
            self._logger.error(
                f'Cannot handle failed message - the channel is closed. '
                f'The message will be redelivered. Original failure - '
                f'{str(type(exception))}: {str(exception)}')
            return

        errorRetriesHeaderKey = pikaProperties.errorRetriesHeaderKey
        # A copy, not the live incoming header dict. 1.x mutated the pika frame's own dict in place.
        updatedHeaders: dict = dict(incomingMessage.get(PikaConstants.DATA_KEY_HEADERS, None) or {})
        retries = self._GetRetries(updatedHeaders, errorRetriesHeaderKey) + 1
        updatedHeaders[errorRetriesHeaderKey] = retries
        destinationQueue = listenerQueue

        messageId = updatedHeaders.get(pikaProperties.messageIdHeaderKey, None)
        self._logger.info(f'Handling failed message with id {messageId} for the {retries} time.')

        if retries > self._maxRetries >= 0 or destinationQueue is None:
            destinationQueue = self._errorQueue
            declaredQueue = await PikaTools.CreateDurableQueue(channel, destinationQueue,
                                                              settings=self._errorQueueSettings)
            # Commands route through the direct exchange on the queue's own name, so the error queue
            # needs that binding. 1.x got it implicitly from the per-send queue_bind in BasicSend;
            # now that the per-send bind is gone it has to be explicit, or failed messages would
            # silently never arrive.
            await PikaTools.BindQueue(declaredQueue, data[PikaConstants.DATA_KEY_DIRECT_EXCHANGE],
                                      destinationQueue)
            self._logger.info(f'Moving failed message with id {messageId} '
                              f'to error queue {destinationQueue}')
        elif self._delay > 0:
            deferredTime = self._GetDelayedBackoffTime(retries, pikaProperties, self._delay, self._backoff)
            deferredTimeStr = pikaProperties.DatetimeToString(deferredTime)
            updatedHeaders[pikaProperties.deferredTimeHeaderKey] = deferredTimeStr
            self._logger.info(f'Deferring failed message with id {messageId} to {deferredTimeStr}')

        await PikaOutgoing.ResendMessage(data,
                                        destinationQueue=destinationQueue,
                                        headers=updatedHeaders,
                                        exception=exception)
        # Guarded, and ordered after the resend so a failed ack means a duplicate copy rather than a
        # lost message. At-least-once is the documented contract.
        await PikaTools.SafeAcknowledgeMessage(message, logger=self._logger)

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
