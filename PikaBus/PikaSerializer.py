import json
import logging
from PikaBus.abstractions.AbstractPikaSerializer import AbstractPikaSerializer


class PikaSerializer(AbstractPikaSerializer):
    def __init__(self,
                 contentEncoding: str = 'utf-8',
                 logger=logging.getLogger(__name__)):
        """
        :param str contentEncoding: Charset used when encoding/decoding string to bytes
        :param logging logger: Logging object
        """
        self._contentEncoding = contentEncoding
        self._defaultContentType = f'application/json'
        self._logger = logger

    def Serialize(self, data: dict, payload: dict):
        if payload is None:
            payload = {}
        return json.dumps(payload).encode(self._contentEncoding), self._defaultContentType, self._contentEncoding

    def Deserialize(self, data: dict, body: bytes):
        return json.loads(body)
