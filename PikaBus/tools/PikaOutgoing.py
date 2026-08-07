import asyncio

import aio_pika

from PikaBus.abstractions.AbstractPikaSerializer import AbstractPikaSerializer
from PikaBus.abstractions.AbstractPikaProperties import AbstractPikaProperties
from PikaBus.tools import PikaConstants, PikaTools


class PikaBusTransactionError(Exception):
    """
    Raised when a transaction flush could not publish every outgoing message.

    PikaBus transactions are an in-memory outbox, not an AMQP transaction, so a flush is not atomic:
    some messages may already be on the broker when a later one fails. This exception reports exactly
    which ones, instead of leaving it implicit.
    """

    def __init__(self, published: list, failed: list):
        self.published = published
        self.failed = failed
        firstError = failed[0][1] if failed else None
        super().__init__(
            f'Failed publishing {len(failed)} of {len(published) + len(failed)} outgoing messages. '
            f'{len(published)} were published and cannot be un-published. First error - '
            f'{str(type(firstError))}: {str(firstError)}')


async def ResendMessage(data: dict,
                        intent: str = PikaConstants.INTENT_COMMAND,
                        destinationQueue: str = None,
                        body: bytes = None,
                        headers: dict = None,
                        exchange: str = None,
                        exception: Exception = None):
    incomingMessage = data[PikaConstants.DATA_KEY_INCOMING_MESSAGE]
    if destinationQueue is None:
        destinationQueue: str = data[PikaConstants.DATA_KEY_LISTENER_QUEUE]
    if body is None:
        body = incomingMessage[PikaConstants.DATA_KEY_BODY]
    if headers is None:
        # dict(...) rather than the live header dict. PikaBus 1.x passed the incoming pika header
        # frame's own dict here and mutated it in place, which only worked by accident.
        headers = dict(incomingMessage.get(PikaConstants.DATA_KEY_HEADERS, None) or {})
    outgoingMessage = GetOutgoingMessage(data, destinationQueue,
                                         intent=intent,
                                         headers=headers,
                                         exchange=exchange,
                                         exception=exception)

    outgoingMessage[PikaConstants.DATA_KEY_BODY] = body
    outgoingMessage[PikaConstants.DATA_KEY_CONTENT_TYPE] = None
    await SendOrPublishOutgoingMessage(data, outgoingMessage)


async def SendOrPublishOutgoingMessages(data: dict):
    """
    Flush the outbox.

    All messages are published concurrently and gathered, so the whole flush costs one round trip
    instead of N. If any publish fails, PikaBusTransactionError reports which succeeded and which
    did not - PikaBus 1.x published sequentially and simply stopped at the first failure, leaving
    the remaining messages silently unsent and the outbox uncleared.
    """
    outgoingMessages = data[PikaConstants.DATA_KEY_OUTGOING_MESSAGES]
    if not outgoingMessages:
        return
    results = await asyncio.gather(
        *[SendOrPublishOutgoingMessage(data, outgoingMessage) for outgoingMessage in outgoingMessages],
        return_exceptions=True)
    published, failed = [], []
    for outgoingMessage, result in zip(outgoingMessages, results):
        if isinstance(result, BaseException):
            failed.append((outgoingMessage, result))
        else:
            published.append(outgoingMessage)
    if failed:
        raise PikaBusTransactionError(published, failed)


async def SendOrPublishOutgoingMessage(data: dict, outgoingMessage: dict):
    logger = data[PikaConstants.DATA_KEY_LOGGER]
    channel: aio_pika.abc.AbstractChannel = data[PikaConstants.DATA_KEY_CHANNEL]
    propertyBuilder: AbstractPikaProperties = data[PikaConstants.DATA_KEY_PROPERTY_BUILDER]
    message: aio_pika.Message = propertyBuilder.GetPikaProperties(data, outgoingMessage)
    exchangeName = outgoingMessage[PikaConstants.DATA_KEY_EXCHANGE]
    topicOrQueue = outgoingMessage[PikaConstants.DATA_KEY_TOPIC]
    intent = outgoingMessage[PikaConstants.DATA_KEY_INTENT]
    mandatory = outgoingMessage[PikaConstants.DATA_KEY_MANDATORY_DELIVERY]

    if intent == PikaConstants.INTENT_EVENT:
        if exchangeName is None:
            exchangeName = data[PikaConstants.DATA_KEY_TOPIC_EXCHANGE]
    elif intent == PikaConstants.INTENT_COMMAND:
        if exchangeName is None:
            exchangeName = data[PikaConstants.DATA_KEY_DIRECT_EXCHANGE]
    else:
        msg = f'Outgoing type {intent} is not implemented!'
        logger.error(msg)
        raise Exception(msg)

    # ensure=False gets a publishable exchange handle with no passive declare round trip.
    exchange = await channel.get_exchange(exchangeName, ensure=False)

    if intent == PikaConstants.INTENT_COMMAND:
        # A command routes through the direct exchange on the destination queue's own name, so that
        # binding has to exist. PikaBus 1.x re-created it on every single send; the bind cache does
        # it once per destination per channel instead.
        binder = data.get(PikaConstants.DATA_KEY_BIND_CACHE, None)
        if binder is not None:
            await binder(channel, exchangeName, topicOrQueue)

    await PikaTools.BasicPublish(exchange, topicOrQueue, message, mandatory=mandatory)


def AppendOutgoingMessage(data: dict, payload: dict, topicOrQueue: str,
                          intent: str = PikaConstants.INTENT_EVENT,
                          headers: dict = None,
                          messageType: str = None,
                          exchange: str = None,
                          mandatory: bool = True,
                          exception: Exception = None):
    outgoingMessage = GetOutgoingMessage(data, topicOrQueue,
                                         payload=payload,
                                         intent=intent,
                                         headers=headers,
                                         messageType=messageType,
                                         exchange=exchange,
                                         mandatory=mandatory,
                                         exception=exception)

    if not PikaConstants.DATA_KEY_OUTGOING_MESSAGES in data:
        data[PikaConstants.DATA_KEY_OUTGOING_MESSAGES] = []
    data[PikaConstants.DATA_KEY_OUTGOING_MESSAGES].append(outgoingMessage)


def GetOutgoingMessage(data: dict, topicOrQueue: str,
                       payload: dict = None,
                       intent: str = PikaConstants.INTENT_EVENT,
                       headers: dict = None,
                       messageType: str = None,
                       exchange: str = None,
                       mandatory: bool = True,
                       exception: Exception = None):
    if headers is None:
        headers = {}
    serializer: AbstractPikaSerializer = data[PikaConstants.DATA_KEY_SERIALIZER]
    body, contentType, encoding = serializer.Serialize(data, payload)
    outgoingMessage = {
        PikaConstants.DATA_KEY_INTENT: intent,
        PikaConstants.DATA_KEY_PAYLOAD: payload,
        PikaConstants.DATA_KEY_TOPIC: topicOrQueue,
        PikaConstants.DATA_KEY_BODY: body,
        PikaConstants.DATA_KEY_CONTENT_TYPE: contentType,
        PikaConstants.DATA_KEY_CONTENT_ENCODING: encoding,
        PikaConstants.DATA_KEY_HEADERS: headers,
        PikaConstants.DATA_KEY_MESSAGE_TYPE: messageType,
        PikaConstants.DATA_KEY_EXCHANGE: exchange,
        PikaConstants.DATA_KEY_MANDATORY_DELIVERY: mandatory,
        PikaConstants.DATA_KEY_EXCEPTION: exception,
    }

    return outgoingMessage
