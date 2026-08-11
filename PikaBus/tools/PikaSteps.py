import asyncio

import aio_pika

from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus
from PikaBus.abstractions.AbstractPikaErrorHandler import AbstractPikaErrorHandler
from PikaBus.abstractions.AbstractPikaMessageHandler import AbstractPikaMessageHandler
from PikaBus.abstractions.AbstractPikaProperties import AbstractPikaProperties
from PikaBus.tools import PikaConstants, PikaOutgoing, PikaTools


async def HandleNextStep(pipelineIterator: iter, data: dict):
    """
    Advance the pipeline one step.

    Each step calls this itself, so the pipeline is a nest of awaits rather than a loop. That is what
    lets TryHandleMessageInPipeline wrap everything downstream in one try/except - exactly as the
    synchronous 1.x call stack did.

    Steps may be `async def` or plain `def`, so a custom 1.x pipeline step still works.
    """
    nextStep = next(pipelineIterator, None)
    if nextStep is None:
        return
    await PikaTools.CallMaybeAwaitable(nextStep, pipelineIterator, data)


async def TryHandleMessageInPipeline(pipelineIterator: iter, data: dict):
    logger = data[PikaConstants.DATA_KEY_LOGGER]
    try:
        await HandleNextStep(pipelineIterator, data)
    except asyncio.CancelledError:
        # Shutdown, not a message failure. Leave the message unacked so the broker redelivers it.
        raise
    except Exception as exception:
        logger.exception(str(exception))
        errorHandler: AbstractPikaErrorHandler = data[PikaConstants.DATA_KEY_ERROR_HANDLER]
        # Deliberately not guarded here: if the error handler itself fails, the message callback in
        # PikaBusSetup handles the double fault. Swallowing it here would hide that path.
        await errorHandler.HandleFailure(data, exception)


async def CheckIfMessageIsDeferred(pipelineIterator: iter, data: dict):
    """
    Republish a not-yet-due message back to its queue instead of letting the pipeline continue.

    The message bounces off the broker until its DeferredTime has passed, as it did in 1.x. It is
    deliberately not awaited in-process: this consumer runs at most `concurrency` handlers at a
    time, so sleeping on a deferred message would hold both its prefetch slot and a concurrency
    slot, and a single long defer would stall every other message on the queue behind it.

    The cost is one republish/ack round trip per redelivery, with nothing throttling the loop, so a
    long defer is chatty. For long delays prefer a broker-side mechanism - a per-message TTL on a
    queue with x-dead-letter-exchange, or the delayed message exchange plugin.
    """
    logger = data[PikaConstants.DATA_KEY_LOGGER]
    pikaProperties: AbstractPikaProperties = data[PikaConstants.DATA_KEY_PROPERTY_BUILDER]
    incomingMessage = data[PikaConstants.DATA_KEY_INCOMING_MESSAGE]
    message: aio_pika.abc.AbstractIncomingMessage = incomingMessage[PikaConstants.DATA_KEY_MESSAGE]
    headers: dict = incomingMessage[PikaConstants.DATA_KEY_HEADERS]
    deferredTimeHeaderKey = pikaProperties.deferredTimeHeaderKey

    if deferredTimeHeaderKey in headers:
        deferredTime = pikaProperties.StringToDatetime(str(headers[deferredTimeHeaderKey]))
        now = pikaProperties.StringToDatetime(pikaProperties.DatetimeToString())
        remaining = (deferredTime - now).total_seconds()
        if remaining > 0:
            logger.debug(f'Message is deferred for another {remaining} seconds. Republishing it.')
            await PikaOutgoing.ResendMessage(data)
            await PikaTools.SafeAcknowledgeMessage(message, logger=logger)
            return
    await HandleNextStep(pipelineIterator, data)


async def SerializeMessage(pipelineIterator: iter, data: dict):
    body: bytes = data[PikaConstants.DATA_KEY_INCOMING_MESSAGE][PikaConstants.DATA_KEY_BODY]
    payload: dict = data[PikaConstants.DATA_KEY_SERIALIZER].Deserialize(data, body)
    data[PikaConstants.DATA_KEY_INCOMING_MESSAGE][PikaConstants.DATA_KEY_PAYLOAD] = payload
    await HandleNextStep(pipelineIterator, data)


async def HandleMessage(pipelineIterator: iter, data: dict):
    """
    Invoke every registered message handler inside one bus transaction.

    Handlers may be `async def` or plain `def`, and may be either an AbstractPikaMessageHandler
    subclass or any callable taking **kwargs.

    A plain `def` handler cannot publish, because bus.Send/Publish/Reply/Defer are coroutines in 2.0 -
    calling one without awaiting it silently does nothing. Handlers that publish must be `async def`.
    A plain `def` handler also runs on the event loop, so it must not block.
    """
    bus: AbstractPikaBus = data[PikaConstants.DATA_KEY_BUS]
    payload: dict = data[PikaConstants.DATA_KEY_INCOMING_MESSAGE][PikaConstants.DATA_KEY_PAYLOAD]
    messageHandlers: list = data[PikaConstants.DATA_KEY_MESSAGE_HANDLERS]

    bus.StartTransaction()
    for messageHandler in messageHandlers:
        if isinstance(messageHandler, AbstractPikaMessageHandler):
            await PikaTools.CallMaybeAwaitable(messageHandler.HandleMessage,
                                               data=data, bus=bus, payload=payload)
        else:
            await PikaTools.CallMaybeAwaitable(messageHandler,
                                               data=data, bus=bus, payload=payload)
    await bus.CommitTransaction()
    await HandleNextStep(pipelineIterator, data)


async def AcknowledgeMessage(pipelineIterator: iter, data: dict):
    logger = data[PikaConstants.DATA_KEY_LOGGER]
    message: aio_pika.abc.AbstractIncomingMessage = \
        data[PikaConstants.DATA_KEY_INCOMING_MESSAGE][PikaConstants.DATA_KEY_MESSAGE]
    # Guarded: if a robust channel was recovered while the handler ran, the delivery tag is stale and
    # ack raises. PikaBus guarantees at-least-once, so the broker redelivering is the correct outcome.
    await PikaTools.SafeAcknowledgeMessage(message, logger=logger)
    await HandleNextStep(pipelineIterator, data)
