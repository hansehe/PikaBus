import json

from PikaBus.tools import PikaConstants
from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus
from PikaBus.abstractions.AbstractPikaMessageHandler import AbstractPikaMessageHandler


class PikaMessageHandler(AbstractPikaMessageHandler):
    """An asynchronous AbstractPikaMessageHandler subclass."""

    def __init__(self, actAsErrorHandler=False):
        self.receivedIds = []
        self.actAsErrorHandler = actAsErrorHandler

    async def HandleMessage(self, data: dict, bus: AbstractPikaBus, payload: dict):
        print(json.dumps(payload, indent=4, sort_keys=True))
        id = payload['id']
        failing = payload['failing']
        if self.actAsErrorHandler and failing:
            headers = data[PikaConstants.DATA_KEY_INCOMING_MESSAGE][PikaConstants.DATA_KEY_HEADERS]
            errorDetails = headers[f'PikaBus.{PikaConstants.HEADER_KEY_ERROR_DETAILS}']
            print(errorDetails)
        elif failing:
            raise Exception(f'Failing message {id} as Im told!')
        self.receivedIds.append(id)


class SyncPikaMessageHandler(AbstractPikaMessageHandler):
    """
    A synchronous AbstractPikaMessageHandler subclass.

    Deliberately does not publish - the bus methods are coroutines in 2.0, so a synchronous handler
    cannot use them.
    """

    def __init__(self):
        self.receivedIds = []

    def HandleMessage(self, data: dict, bus: AbstractPikaBus, payload: dict):
        self.receivedIds.append(payload['id'])
