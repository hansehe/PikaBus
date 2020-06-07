from PikaBus.abstractions.AbstractPikaSerializer import AbstractPikaSerializer
from PikaBus.abstractions.AbstractPikaProperties import AbstractPikaProperties
from PikaBus.tools import PikaConstants, PikaTools
import pika


def ResendMessage(data: dict,
                  intent: str = PikaConstants.INTENT_COMMAND,
                  destinationQueue: str = None,
                  body: bytes = None,
                  headers: dict = None,
                  exchange: str = None,
                  exception: Exception = None):
    if destinationQueue is None:
        destinationQueue: str = data[PikaConstants.DATA_KEY_LISTENER_QUEUE]
    if body is None:
        body = data[PikaConstants.DATA_KEY_INCOMING_MESSAGE][PikaConstants.DATA_KEY_BODY]
    if headers is None:
        headers = data[PikaConstants.DATA_KEY_INCOMING_MESSAGE][PikaConstants.DATA_KEY_HEADER_FRAME].headers
    outgoingMessage = GetOutgoingMessage(data, destinationQueue,
                                         intent=intent,
                                         headers=headers,
                                         exchange=exchange,
                                         exception=exception)

    outgoingMessage[PikaConstants.DATA_KEY_BODY] = body
    outgoingMessage[PikaConstants.DATA_KEY_CONTENT_TYPE] = None
    SendOrPublishOutgoingMessage(data, outgoingMessage)


def SendOrPublishOutgoingMessages(data: dict):
    outgoingMessages = data[PikaConstants.DATA_KEY_OUTGOING_MESSAGES]
    for outgoingMessage in outgoingMessages:
        SendOrPublishOutgoingMessage(data, outgoingMessage)


def SendOrPublishOutgoingMessage(data: dict, outgoingMessage: dict):
    logger = data[PikaConstants.DATA_KEY_LOGGER]
    channel: pika.adapters.blocking_connection.BlockingChannel = data[PikaConstants.DATA_KEY_CHANNEL]
    propertyBuilder: AbstractPikaProperties = data[PikaConstants.DATA_KEY_PROPERTY_BUILDER]
    properties = propertyBuilder.GetPikaProperties(data, outgoingMessage)
    exchange = outgoingMessage[PikaConstants.DATA_KEY_EXCHANGE]
    topicOrQueue = outgoingMessage[PikaConstants.DATA_KEY_TOPIC]
    body = outgoingMessage[PikaConstants.DATA_KEY_BODY]
    intent = outgoingMessage[PikaConstants.DATA_KEY_INTENT]
    mandatory = outgoingMessage[PikaConstants.DATA_KEY_MANDATORY_DELIVERY]
    if intent == PikaConstants.INTENT_EVENT:
        if exchange is None:
            exchange = data[PikaConstants.DATA_KEY_TOPIC_EXCHANGE]
        PikaTools.BasicPublish(channel, exchange, topicOrQueue, body,
                               properties=properties,
                               mandatory=mandatory)
    elif intent == PikaConstants.INTENT_COMMAND:
        if exchange is None:
            exchange = data[PikaConstants.DATA_KEY_DIRECT_EXCHANGE]
        PikaTools.BasicSend(channel, exchange, topicOrQueue, body,
                            properties=properties,
                            mandatory=mandatory)
    else:
        msg = f'Outgoing type {intent} is not implemented!'
        logger.exception(msg)
        raise Exception(msg)


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
