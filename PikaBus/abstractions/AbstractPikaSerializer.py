import abc


class AbstractPikaSerializer(abc.ABC):
    @abc.abstractmethod
    def Serialize(self, data: dict, payload: dict):
        """
        :param dict data: General data holder dictionary
        :param payload: payload to serialize
        :return: (bytes, str) body, contentType
        """
        pass

    @abc.abstractmethod
    def Deserialize(self, data: dict, body: bytes):
        """
        :param dict data: General data holder dictionary
        :param bytes body: Body to deserialize
        :return: dict
        """
        pass
