import abc
import datetime


class AbstractPikaProperties(abc.ABC):
    @abc.abstractmethod
    def GetPikaProperties(self, data: dict, outgoingMessage: dict):
        """
        :param dict data: General data holder
        :param dict outgoingMessage: Outgoing message
        :rtype pika.spec.BasicProperties
        """
        pass

    @abc.abstractmethod
    def DatetimeToString(self,
                         time: datetime.datetime = None):
        """
        :param datetime.datetime time: Optional time to convert to string. Will return utcnow() if it is None.
        :rtype: str
        """
        pass

    @abc.abstractmethod
    def StringToDatetime(self, strTime: str):
        """
        :param str strTime: Timestamp string to convert to datetime.
        :rtype: datetime.datetime
        """
        pass

    @property
    @abc.abstractmethod
    def messageIdHeaderKey(self):
        pass

    @property
    @abc.abstractmethod
    def correlationIdHeaderKey(self):
        pass

    @property
    @abc.abstractmethod
    def timeSentHeaderKey(self):
        pass

    @property
    @abc.abstractmethod
    def replyToAddressHeaderKey(self):
        pass

    @property
    @abc.abstractmethod
    def originatingAddressHeaderKey(self):
        pass

    @property
    @abc.abstractmethod
    def intentHeaderKey(self):
        pass

    @property
    @abc.abstractmethod
    def messsageTypeHeaderKey(self):
        pass

    @property
    @abc.abstractmethod
    def contentTypeHeaderKey(self):
        pass

    @property
    @abc.abstractmethod
    def errorDetailsHeaderKey(self):
        pass

    @property
    @abc.abstractmethod
    def sourceQueueHeaderKey(self):
        pass

    @property
    @abc.abstractmethod
    def errorRetriesHeaderKey(self):
        pass

    @property
    @abc.abstractmethod
    def deferredTimeHeaderKey(self):
        pass


