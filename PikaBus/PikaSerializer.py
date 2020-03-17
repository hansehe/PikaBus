import json
import logging
from PikaBus.abstractions.AbstractPikaSerializer import AbstractPikaSerializer


class PikaSerializer(AbstractPikaSerializer):
    def __init__(self,
                 defaultContentType: str = 'application/json;charset=utf-8',
                 logger=logging.getLogger(__name__)):
        """
        :param str defaultContentType: Default content type used when serializing.
        :param logging logger: Logging object
        """
        self._defaultContentType = defaultContentType
        self._logger = logger

    def Serialize(self, data: dict, payload: dict):
        return json.dumps(payload), self._defaultContentType

    def Deserialize(self, data: dict, body: bytes):
        return json.loads(body)
