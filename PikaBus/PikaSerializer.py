import json
import logging
from PikaBus.abstractions.AbstractPikaSerializer import AbstractPikaSerializer


class PikaSerializer(AbstractPikaSerializer):
    def __init__(self,
                 charset: str = 'utf-8',
                 logger=logging.getLogger(__name__)):
        """
        :param str charset: Charset used when encoding/decoding string to bytes
        :param logging logger: Logging object
        """
        self._charset = charset
        self._defaultContentType = f'application/json;charset={self._charset}'
        self._logger = logger

    def Serialize(self, data: dict, payload: dict):
        return json.dumps(payload).encode(self._charset), self._defaultContentType

    def Deserialize(self, data: dict, body: bytes):
        return json.loads(body.decode(self._charset))
