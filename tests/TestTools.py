import asyncio
import os
import uuid
from typing import Callable

import aio_pika

from PikaBus import PikaBusSetup
from PikaBus import PikaErrorHandler
from PikaBus.tools import PikaTools


def GetDefaultConnectionUrl():
    """
    The broker url under test.

    PIKABUS_TEST_AMQP_URL wins, which is how CI points at a service container. Otherwise the host is
    'rabbitmq' inside the test container and 'localhost' on a developer machine.
    """
    url = os.getenv('PIKABUS_TEST_AMQP_URL', None)
    if url:
        return url
    host = 'localhost'
    if os.getenv('RUNNING_IN_CONTAINER', 'false') == 'true':
        host = 'rabbitmq'
    return f'amqp://amqp:amqp@{host}:5672/'


def GetRandomQueue(prefix: str = 'test'):
    id = str(uuid.uuid1())
    return f'pika-{prefix}-{id}'


def GetRandomTopic():
    id = str(uuid.uuid1())
    return f'pika-topic-{id}'


def GetPikaBusSetup(listenerQueue: str = None,
                    connectionUrl: str = None,
                    errorQueue: str = 'error',
                    topics: list = None,
                    maxRetries: int = 1,
                    **kwargs):
    if connectionUrl is None:
        connectionUrl = GetDefaultConnectionUrl()
    if topics is None:
        topics = []
    pikaErrorHandler = PikaErrorHandler.PikaErrorHandler(errorQueue=errorQueue, maxRetries=maxRetries)
    return PikaBusSetup.PikaBusSetup(connectionUrl,
                                     defaultListenerQueue=listenerQueue,
                                     defaultSubscriptions=topics,
                                     pikaErrorHandler=pikaErrorHandler,
                                     retryParams={'tries': 10},
                                     stopConsumersAtExit=False,
                                     **kwargs)


def GetPayload(id=None, failing=False, reply=False, topic=''):
    if id is None:
        id = str(uuid.uuid1())
    return {
        'id': id,
        'failing': failing,
        'reply': reply,
        'topic': topic,
    }


async def CompleteTask(tasks: list):
    return await asyncio.gather(*tasks, return_exceptions=True)


async def WaitUntilRabbitLives(connectionUrl: str = None):
    if connectionUrl is None:
        connectionUrl = GetDefaultConnectionUrl()
    tries = 0
    maxTries = 30
    while tries < maxTries:
        try:
            # connect, not connect_robust - a robust connection would sit in its own reconnect loop
            # instead of letting an attempt fail, so this would never make progress.
            connection = await aio_pika.connect(connectionUrl, timeout=2)
            await connection.close()
            return
        except Exception:
            pass
        tries += 1
        await asyncio.sleep(1)
    raise Exception(f"Cannot connect to rabbitmq at {connectionUrl}!")


async def WaitUntil(predicate: Callable, timeout: float = 30, interval: float = 0.05):
    """
    Poll until predicate is truthy, or the timeout expires.

    Replaces the fixed time.sleep(5) the 1.x suite used: it returns as soon as the condition holds
    rather than always paying the full wait, and it can fail loudly instead of flakily.

    :param def predicate: Synchronous or asynchronous callable returning a truthy value when done.
    :param float timeout: Seconds before giving up.
    :param float interval: Seconds between polls.
    :rtype: bool - True if the predicate became truthy in time.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        if await PikaTools.CallMaybeAwaitable(predicate):
            return True
        if loop.time() >= deadline:
            return False
        await asyncio.sleep(interval)
