import abc
import asyncio
import concurrent.futures
from PikaBus.abstractions.AbstractPikaMessageHandler import AbstractPikaMessageHandler


class AbstractPikaBusSetup(abc.ABC):
    @property
    @abc.abstractmethod
    def pipeline(self):
        """
        returns pipeline [list]: A list of function steps to go through when handling a message.
        Each function must have these parameters:
        - pipelineIterator: iter
        - data: dict
        """
        pass

    @property
    @abc.abstractmethod
    def channels(self):
        """
        returns all open channels as a dictionary with keys as the channel ids.
        :rtype: dict{id: pika.adapters.blocking_connection.BlockingChannel}
        """
        pass

    @property
    @abc.abstractmethod
    def messageHandlers(self):
        """
        returns all registered message handlers.
        :rtype: list[AbstractPikaMessageHandler]
        """
        pass

    @abc.abstractmethod
    def Start(self):
        """
        Start blocking bus consumer channel.
        """
        pass

    @abc.abstractmethod
    def Stop(self, channelId: str = None):
        """
        Stop blocking bus consumer channel.
        :param str channelId: Optional channel id. Get open channels with self.channels().
        """
        pass

    @abc.abstractmethod
    def StartAsync(self,
                   consumers: int = 1,
                   loop: asyncio.AbstractEventLoop = None,
                   executor: concurrent.futures.ThreadPoolExecutor = None):
        """
        Start consumers as asynchronous tasks.
        :param int consumers: Number of consumers to start.
        :param asyncio.AbstractEventLoop loop: Event loop. Defaults to current event loop if None.
        :param executor: concurrent.futures.ThreadPoolExecutor executor: Executor. Defaults to current executor if None.
        :rtype: [concurrent.futures.Future]
        """
        pass

    @abc.abstractmethod
    def CreateBus(self):
        """
        Create bus with separate channel.
        :rtype: PikaBus.abstractions.AbstractPikaBus.AbstractPikaBus
        """
        pass

    @abc.abstractmethod
    def AddMessageHandler(self, messageHandler: AbstractPikaMessageHandler):
        """
        :param PikaBus.abstractions.AbstractPikaMessageHandler.AbstractPikaMessageHandler messageHandler: Message handler.
        May also be a method with parameters matching AbstractPikaMessageHandler.HandleMessage(..)
        """
        pass
