import abc


class AbstractPikaBus(abc.ABC):
    @abc.abstractmethod
    def Send(self, payload: dict, queue: str = None, headers: dict = {}, messageType: str = None, exchange: str = None):
        """
        :param dict payload: Payload to send
        :param str queue: Destination queue. If None, the it it sent back to the listener queue.
        :param dict headers: Optional headers to add or override
        :param str messageType: Specify message type if necessary.
        :param str exchange: Optional exchange to override with.
        """
        pass

    @abc.abstractmethod
    def Publish(self, payload: dict, topic: str, headers: dict = {}, messageType: str = None, exchange: str = None):
        """
        :param dict payload: Payload to send
        :param str topic: Topic.
        :param dict headers: Optional headers to add or override
        :param str messageType: Specify message type if necessary.
        :param str exchange: Optional exchange to override with.
        """
        pass

    @abc.abstractmethod
    def Subscribe(self, topic: str, exchange: str = None):
        """
        :param str topic: Subscribed topic
        :param exchange: Optional exchange to override with.
        """
        pass

    @abc.abstractmethod
    def StartTransaction(self):
        """
        Start a bus transaction. All outgoing messages will be stored in-memory, until CommitTransaction() is triggered.
        """
        pass

    @abc.abstractmethod
    def CommitTransaction(self):
        """
        Commit ongoing bus transaction to send in-memory stored outgoing messages.
        """
        pass
