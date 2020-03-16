import abc
from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus


class AbstractPikaMessageHandler(abc.ABC):
    @abc.abstractmethod
    def HandleMessage(self, data: dict, bus: AbstractPikaBus, payload: dict):
        """
        :param dict data: General data holder
        :param AbstractPikaBus bus: Bus instance used during the message handling.
        :param dict payload: Message payload
        """
        pass
