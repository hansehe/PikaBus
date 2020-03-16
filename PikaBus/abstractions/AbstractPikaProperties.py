import abc


class AbstractPikaProperties(abc.ABC):
    @abc.abstractmethod
    def GetPikaProperties(self, data: dict, outgoingMessage: dict):
        """
        :param dict data: General data holder
        :param dict outgoingMessage: Outgoing message
        :rtype pika.spec.BasicProperties
        """
        pass


