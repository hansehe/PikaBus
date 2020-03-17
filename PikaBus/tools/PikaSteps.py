import pika
from pika import frame
from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus
from PikaBus.abstractions.AbstractPikaErrorHandler import AbstractPikaErrorHandler
from PikaBus.abstractions.AbstractPikaMessageHandler import AbstractPikaMessageHandler
from PikaBus.abstractions.AbstractPikaProperties import AbstractPikaProperties
from PikaBus.tools import PikaConstants, PikaOutgoing


def HandleNextStep(pipelineIterator: iter, data: dict):
    nextStep = next(pipelineIterator, None)
    if nextStep is None:
        return
    nextStep(pipelineIterator, data)


def TryHandleMessageInPipeline(pipelineIterator: iter, data: dict):
    try:
        HandleNextStep(pipelineIterator, data)
    except Exception as exception:
        logger = data[PikaConstants.DATA_KEY_LOGGER]
        logger.exception(str(exception))
        errorHandler: AbstractPikaErrorHandler = data[PikaConstants.DATA_KEY_ERROR_HANDLER]
        errorHandler.HandleFailure(data, exception)


def CheckIfMessageIsDeferred(pipelineIterator: iter, data: dict):
    channel: pika.adapters.blocking_connection.BlockingChannel = data[PikaConstants.DATA_KEY_CHANNEL]
    pikaProperties: AbstractPikaProperties = data[PikaConstants.DATA_KEY_PROPERTY_BUILDER]
    methodFrame: frame.Method = data[PikaConstants.DATA_KEY_INCOMING_MESSAGE][PikaConstants.DATA_KEY_METHOD_FRAME]
    headers: dict = data[PikaConstants.DATA_KEY_INCOMING_MESSAGE][PikaConstants.DATA_KEY_HEADER_FRAME].headers
    deferredTimeHeaderKey = pikaProperties.deferredTimeHeaderKey
    if deferredTimeHeaderKey in headers:
        deferredTime = pikaProperties.StringToDatetime(headers[deferredTimeHeaderKey])
        now = pikaProperties.StringToDatetime(pikaProperties.DatetimeToString())
        if deferredTime >= now:
            PikaOutgoing.ResendMessage(data)
            channel.basic_ack(methodFrame.delivery_tag)
            return
    HandleNextStep(pipelineIterator, data)


def SerializeMessage(pipelineIterator: iter, data: dict):
    body: bytes = data[PikaConstants.DATA_KEY_INCOMING_MESSAGE][PikaConstants.DATA_KEY_BODY]
    payload: dict = data[PikaConstants.DATA_KEY_SERIALIZER].Deserialize(data, body)
    data[PikaConstants.DATA_KEY_INCOMING_MESSAGE][PikaConstants.DATA_KEY_PAYLOAD] = payload
    HandleNextStep(pipelineIterator, data)


def HandleMessage(pipelineIterator: iter, data: dict):
    bus: AbstractPikaBus = data[PikaConstants.DATA_KEY_BUS]
    payload: dict = data[PikaConstants.DATA_KEY_INCOMING_MESSAGE][PikaConstants.DATA_KEY_PAYLOAD]
    messageHandlers: list = data[PikaConstants.DATA_KEY_MESSAGE_HANDLERS]

    bus.StartTransaction()
    for messageHandler in messageHandlers:
        if isinstance(messageHandler, AbstractPikaMessageHandler):
            messageHandler.HandleMessage(data=data, bus=bus, payload=payload)
        else:
            messageHandler(data=data, bus=bus, payload=payload)
    bus.CommitTransaction()
    HandleNextStep(pipelineIterator, data)


def AcknowledgeMessage(pipelineIterator: iter, data: dict):
    channel: pika.adapters.blocking_connection.BlockingChannel = data[PikaConstants.DATA_KEY_CHANNEL]
    methodFrame: frame.Method = data[PikaConstants.DATA_KEY_INCOMING_MESSAGE][PikaConstants.DATA_KEY_METHOD_FRAME]
    channel.basic_ack(methodFrame.delivery_tag)
    HandleNextStep(pipelineIterator, data)
