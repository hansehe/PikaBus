import pika
from pika import frame
from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus
from PikaBus.abstractions.AbstractPikaErrorHandler import AbstractPikaErrorHandler
from PikaBus.abstractions.AbstractPikaMessageHandler import AbstractPikaMessageHandler
from PikaBus.tools import PikaConstants


def HandleNextStep(pipelineIterator: iter, data: dict):
    nextStep = next(pipelineIterator, None)
    if nextStep is None:
        return
    nextStep(pipelineIterator, data)


def TryHandleMessageInPipeline(pipelineIterator: iter, data: dict):
    channel: pika.adapters.blocking_connection.BlockingChannel = data[PikaConstants.DATA_KEY_CHANNEL]
    methodFrame: frame.Method = data[PikaConstants.DATA_KEY_INCOMING_MESSAGE][PikaConstants.DATA_KEY_METHOD_FRAME]
    try:
        HandleNextStep(pipelineIterator, data)
        channel.basic_ack(methodFrame.delivery_tag)
    except Exception as exception:
        errorHandler: AbstractPikaErrorHandler = data[PikaConstants.DATA_KEY_ERROR_HANDLER]
        errorHandler.HandleFailure(data, exception)


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

