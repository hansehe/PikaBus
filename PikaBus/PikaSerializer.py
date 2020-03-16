import json
from PikaBus.abstractions.AbstractPikaSerializer import AbstractPikaSerializer


DEFAULT_CONTENT_TYPE = 'application/json;charset=utf-8'


class PikaSerializer(AbstractPikaSerializer):
    def Serialize(self, data: dict, payload: dict):
        return json.dumps(payload), DEFAULT_CONTENT_TYPE

    def Deserialize(self, data: dict, body: bytes):
        return json.loads(body)
