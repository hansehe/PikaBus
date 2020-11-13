from typing import Union, List

import pika
import pika.exceptions
import time
import logging


def CreateDurableQueue(channel: pika.adapters.blocking_connection.BlockingChannel, queue: str,
                       settings: dict = None):
    if settings is None:
        settings = {}
    channel.queue_declare(queue,
                          passive=settings.get('passive', False),
                          durable=settings.get('durable', True),
                          exclusive=settings.get('exclusive', False),
                          auto_delete=settings.get('auto_delete', False),
                          arguments=settings.get('arguments', None))


def CreateExchange(channel: pika.adapters.blocking_connection.BlockingChannel, exchange: str,
                   settings: dict = None):
    if settings is None:
        settings = {}
    channel.exchange_declare(exchange,
                             exchange_type=settings.get('exchange_type', 'direct'),
                             passive=settings.get('passive', False),
                             durable=settings.get('durable', True),
                             auto_delete=settings.get('auto_delete', False),
                             internal=settings.get('internal', False),
                             arguments=settings.get('arguments', None))


def BindQueue(channel: pika.adapters.blocking_connection.BlockingChannel, queue: str, exchange: str, topic: str,
              arguments: dict = None):
    channel.queue_bind(queue, exchange, routing_key=topic, arguments=arguments)


def UnbindQueue(channel: pika.adapters.blocking_connection.BlockingChannel, queue: str, exchange: str, topic: str,
                arguments: dict = None):
    channel.queue_unbind(queue, exchange, routing_key=topic, arguments=arguments)


def AssertDurableQueueExists(connection: pika.BlockingConnection, queue: str, retries: int = 0, logger=logging.getLogger(__name__)):
    count = 0
    while count <= retries:
        channel: pika.adapters.blocking_connection.BlockingChannel = connection.channel()
        try:
            channel.queue_declare(queue, durable=True, passive=True)
            channel.close()
            return
        except Exception as e:
            count += 1
            if count <= retries:
                time.sleep(1)
    msg = f"Queue {queue} does not exist!"
    logger.error(msg)
    raise Exception(msg)


def SafeCloseChannel(channel: pika.BlockingConnection.channel, acceptAllFailures: bool = True):
    if channel.is_closed:
        return
    try:
        channel.close()
    except pika.exceptions.ChannelWrongStateError:
        # channel already closed
        pass
    except:
        if not acceptAllFailures:
            raise


def SafeCloseConnection(connection: pika.BlockingConnection, acceptAllFailures: bool = True):
    if connection.is_closed:
        return
    try:
        connection.close()
    except pika.exceptions.ConnectionWrongStateError:
        # connection already closed
        pass
    except:
        if not acceptAllFailures:
            raise


def BasicSend(channel: pika.adapters.blocking_connection.BlockingChannel,
              exchange: str, destination: str, body: bytes,
              properties: pika.spec.BasicProperties = None,
              mandatory: bool = True):
    BindQueue(channel, queue=destination, exchange=exchange, topic=destination)
    channel.basic_publish(exchange, destination, body, properties=properties, mandatory=mandatory)


def BasicPublish(channel: pika.adapters.blocking_connection.BlockingChannel,
                 exchange: str, topic: str, body: bytes,
                 properties: pika.spec.BasicProperties = None,
                 mandatory: bool = True):
    channel.basic_publish(exchange, topic, body, properties=properties, mandatory=mandatory)


def BasicSubscribe(channel: pika.adapters.blocking_connection.BlockingChannel,
                   exchange: str, topic: Union[List[str], str], queue: str,
                   arguments: dict = None):
    if isinstance(topic, list):
        topics = topic
    else:
        topics = [topic]
    for topic in topics:
        if isinstance(topic, dict):
            arguments = topic.get('arguments', None)
            topic = topic.get('topic', None)
        BindQueue(channel, queue, exchange, topic, arguments=arguments)


def BasicUnsubscribe(channel: pika.adapters.blocking_connection.BlockingChannel,
                     exchange: str, topic: Union[List[str], str], queue: str,
                     arguments: dict = None):
    if isinstance(topic, list):
        topics = topic
    else:
        topics = [topic]
    for topic in topics:
        if isinstance(topic, dict):
            arguments = topic.get('arguments', None)
            topic = topic.get('topic', None)
        UnbindQueue(channel, queue, exchange, topic, arguments=arguments)
