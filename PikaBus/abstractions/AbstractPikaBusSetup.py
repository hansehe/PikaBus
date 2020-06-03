import abc
import asyncio
import concurrent.futures
from typing import Union, Callable, List

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
    def connections(self):
        """
        returns all open connections as a dictionary with keys as the connection ids.
        :rtype: dict{id: pika.adapters.blocking_connection}
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
    def Init(self,
             listenerQueue: str = None,
             listenerQueueSettings: dict = None,
             topicExchange: str = None,
             topicExchangeSettings: dict = None,
             directExchange: str = None,
             directExchangeSettings: dict = None,
             subscriptions: Union[List[str], str] = None):
        """
        :param str listenerQueue: Optional listener queue to override default listener queue.
        :param dict listenerQueueSettings: Optional listener queue settings.
        :param str topicExchange: Optional topic exchange to override default topic exchange.
        :param dict topicExchangeSettings: Optional topic exchange settings.
        :param str directExchange: Optional direct exchange to override default direct exchange.
        :param dict directExchangeSettings: Optional direct exchange settings.
        :param [str] | str subscriptions: Optional topic or a list of topics to subscribe, overriding default topic subscriptions.
        Initialize RabbitMq without starting a consumer by creating exchanges and the listener queue.
        """
        pass

    @abc.abstractmethod
    def Start(self,
              listenerQueue: str = None,
              listenerQueueSettings: dict = None,
              topicExchange: str = None,
              topicExchangeSettings: dict = None,
              directExchange: str = None,
              directExchangeSettings: dict = None,
              subscriptions: Union[List[str], str] = None):
        """
        :param str listenerQueue: Optional listener queue to override default listener queue.
        :param dict listenerQueueSettings: Optional listener queue settings.
        :param str topicExchange: Optional topic exchange to override default topic exchange.
        :param dict topicExchangeSettings: Optional topic exchange settings.
        :param str directExchange: Optional direct exchange to override default direct exchange.
        :param dict directExchangeSettings: Optional direct exchange settings.
        :param [str] | str subscriptions: Optional topic or a list of topics to subscribe, overriding default topic subscriptions.
        Start blocking bus consumer channel.
        """
        pass

    @abc.abstractmethod
    def Stop(self,
             channelId: str = None):
        """
        Stop blocking bus consumer channel.
        :param str channelId: Optional channel id. Get open channels with self.channels.
        """
        pass

    @abc.abstractmethod
    def StartAsync(self,
                   consumers: int = 1,
                   listenerQueue: str = None,
                   listenerQueueSettings: dict = None,
                   topicExchange: str = None,
                   topicExchangeSettings: dict = None,
                   directExchange: str = None,
                   directExchangeSettings: dict = None,
                   subscriptions: Union[List[str], str] = None,
                   loop: asyncio.AbstractEventLoop = None,
                   executor: concurrent.futures.ThreadPoolExecutor = None):
        """
        Start consumers as asynchronous tasks.
        :param int consumers: Number of consumers to start.
        :param str listenerQueue: Optional listener queue to override default listener queue.
        :param dict listenerQueueSettings: Optional listener queue settings.
        :param str topicExchange: Optional topic exchange to override default topic exchange.
        :param dict topicExchangeSettings: Optional topic exchange settings.
        :param str directExchange: Optional direct exchange to override default direct exchange.
        :param dict directExchangeSettings: Optional direct exchange settings.
        :param [str] | str subscriptions: Optional topic or a list of topics to subscribe, overriding default topic subscriptions.
        :param asyncio.AbstractEventLoop loop: Event loop. Defaults to current event loop if None.
        :param executor: concurrent.futures.ThreadPoolExecutor executor: Executor. Defaults to current executor if None.
        :rtype: [concurrent.futures.Future]
        """
        pass

    @abc.abstractmethod
    def CreateBus(self,
                  listenerQueue: str = None,
                  topicExchange: str = None,
                  directExchange: str = None,
                  connection=None):
        """
        Create bus with separate channel.
        :param str listenerQueue: Optional listener queue to override default listener queue.
        :param str topicExchange: Optional topic exchange to override default topic exchange.
        :param str directExchange: Optional direct exchange to override default direct exchange.
        :param pika.adapters.blocking_connection connection: Optional connection to reuse an open connection. Get open connections with self.connections.
        :rtype: PikaBus.abstractions.AbstractPikaBus.AbstractPikaBus
        """
        pass

    @abc.abstractmethod
    def AddMessageHandler(self, messageHandler: Union[AbstractPikaMessageHandler, Callable]):
        """
        :param AbstractPikaMessageHandler | def messageHandler: An abstract message handler class or a method with `**kwargs` input.
        """
        pass
