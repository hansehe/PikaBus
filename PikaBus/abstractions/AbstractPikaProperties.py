import abc
import datetime
import warnings


class AbstractPikaProperties(abc.ABC):
    """
    Builds the outgoing aio_pika.Message, including all PikaBus headers.

    Note on subclassing across the 1.x -> 2.0 boundary: members added in 2.0 are deliberately
    concrete with a working default rather than abstract, so an existing 1.x subclass keeps
    instantiating instead of failing with "Can't instantiate abstract class".
    """

    @abc.abstractmethod
    def GetPikaProperties(self, data: dict, outgoingMessage: dict):
        """
        Build the outgoing message, body included.

        Changed in 2.0: returns an aio_pika.Message instead of a pika.spec.BasicProperties, because
        aio-pika carries the body and the properties in one object.

        :param dict data: General data holder
        :param dict outgoingMessage: Outgoing message
        :rtype aio_pika.Message
        """
        pass

    @abc.abstractmethod
    def DatetimeToString(self,
                         time: datetime.datetime = None):
        """
        Serialize a timestamp for a PikaBus header.

        Changed in 2.0: the default format is ISO 8601 with an offset and microseconds, replacing
        1.x's '%m/%d/%Y %H:%M:%S'. A naive datetime is treated as UTC.

        :param datetime.datetime time: Optional time to convert to string. Will return the current UTC time if it is None.
        :rtype: str
        """
        pass

    @abc.abstractmethod
    def StringToDatetime(self, strTime: str):
        """
        Parse a PikaBus header timestamp.

        Changed in 2.0: returns a timezone-aware datetime, so the values the pipeline compares can
        never mix aware and naive and raise a TypeError.

        :param str strTime: Timestamp string to convert to datetime.
        :rtype: datetime.datetime - timezone aware
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

    @property
    def messsageTypeHeaderKey(self):
        """
        Deprecated misspelling of messageTypeHeaderKey, kept so 1.x subclasses that overrode this
        name keep working. Removed in 2.1. The wire header itself was never misspelled.
        """
        warnings.warn('messsageTypeHeaderKey is a misspelling and is deprecated - '
                      'use messageTypeHeaderKey instead.',
                      DeprecationWarning, stacklevel=2)
        return self.messageTypeHeaderKey

    @property
    def messageTypeHeaderKey(self):
        """
        Added in 2.0, replacing the misspelled messsageTypeHeaderKey. Concrete on purpose: making it
        abstract would break every existing subclass. Subclasses that only overrode the old name are
        still honoured, because the default implementation reads it back.
        """
        override = type(self).__dict__.get('messsageTypeHeaderKey', None)
        if override is not None:
            return override.fget(self)
        raise NotImplementedError('messageTypeHeaderKey must be implemented.')

    @property
    def contentEncodingHeaderKey(self):
        """
        Added to the interface in 2.0. It has always existed on PikaProperties; the interface simply
        never declared it. Concrete on purpose, so existing subclasses keep instantiating.
        """
        raise NotImplementedError('contentEncodingHeaderKey must be implemented.')
