import pika
import os
import asyncio
import concurrent.futures
import uuid
import time
from PikaBus import PikaBusSetup
from PikaBus import PikaErrorHandler


def GetDefaultConnectionParams():
    credentials = pika.PlainCredentials('amqp', 'amqp')
    host = 'localhost'
    if os.getenv('RUNNING_IN_CONTAINER', 'false') == 'true':
        host = 'rabbitmq'
    connParams = pika.ConnectionParameters(
        host=host,
        port=5672,
        virtual_host='/',
        credentials=credentials)
    return connParams


def GetRandomQueue(prefix: str = 'test'):
    id = str(uuid.uuid1())
    return f'pika-{prefix}-{id}'


def GetRandomTopic():
    id = str(uuid.uuid1())
    return f'pika-topic-{id}'


def GetPikaBusSetup(listenerQueue: str = None, connParams: pika.ConnectionParameters = None, errorQueue: str = 'error', topics: list = []):
    if connParams is None:
        connParams = GetDefaultConnectionParams()
    pikaErrorHandler = PikaErrorHandler.PikaErrorHandler(errorQueue=errorQueue, maxRetries=1)
    return PikaBusSetup.PikaBusSetup(connParams,
                                     defaultListenerQueue=listenerQueue,
                                     defaultSubscriptions=topics,
                                     pikaErrorHandler=pikaErrorHandler,
                                     retryParams={'tries': 10})


def GetPayload(id = None, failing = False, reply = False, topic = ''):
    if id is None:
        id = str(uuid.uuid1())
    return {
        'id': id,
        'failing': failing,
        'reply': reply,
        'topic': topic,
    }


def CompleteTask(tasks: list):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(asyncio.gather(*tasks))


def WaitUntilRabbitLives(connParams: pika.ConnectionParameters = None):
    if connParams is None:
        connParams = GetDefaultConnectionParams()
    tries = 0
    maxTries = 30
    while tries < maxTries:
        try:
            with pika.BlockingConnection(connParams) as connection:
                channel: pika.adapters.blocking_connection.BlockingChannel = connection.channel()
                channel.close()
                return
        except:
            pass
        tries += 1
        time.sleep(1)
    raise Exception("Cannot connect to rabbitmq!")