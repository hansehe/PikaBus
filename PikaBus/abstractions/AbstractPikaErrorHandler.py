import abc


class AbstractPikaErrorHandler(abc.ABC):
    @abc.abstractmethod
    def HandleFailure(self, data: dict, exception: Exception):
        """
        :param dict data: General data holder
        :param Exception exception: Raised Exception
        """
        pass

