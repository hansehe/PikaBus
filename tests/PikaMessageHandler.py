import json
from PikaBus.tools import PikaConstants
from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus
from PikaBus.abstractions.AbstractPikaMessageHandler import AbstractPikaMessageHandler


class PikaMessageHandler(AbstractPikaMessageHandler):
    def __init__(self, actAsErrorHandler = False):
        self.receivedIds = []
        self.actAsErrorHandler = actAsErrorHandler

    def HandleMessage(self, data: dict, bus: AbstractPikaBus, payload: dict):
        print(json.dumps(payload, indent=4, sort_keys=True))
        id = payload['id']
        failing = payload['failing']
        if self.actAsErrorHandler and failing:
            headers = data[PikaConstants.DATA_KEY_INCOMING_MESSAGE][PikaConstants.DATA_KEY_HEADER_FRAME].headers
            errorDetails = headers[f'PikaBus.{PikaConstants.HEADER_KEY_ERROR_DETAILS}']
            print(errorDetails)
        elif failing:
            raise Exception(f'Failing message {id} as Im told!')
        self.receivedIds.append(id)

