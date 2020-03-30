import pika
import pika.exceptions
import time
import logging


def CreateDurableQueue(channel: pika.adapters.blocking_connection.BlockingChannel, queue: str,
                       arguments: dict = None):
    channel.queue_declare(queue, durable=True, passive=False, arguments=arguments)


def CreateExchange(channel: pika.adapters.blocking_connection.BlockingChannel, exchange: str,
                   exchangeType: str = 'direct', arguments: dict = None):
    channel.exchange_declare(exchange, exchange_type=exchangeType, passive=False, durable=True, arguments=arguments)


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
    logger.exception(msg)
    raise Exception(msg)


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
                   exchange: str, topic: str, queue: str):
    if isinstance(topic, list):
        topics = topic
    else:
        topics = [topic]
    for topic in topics:
        BindQueue(channel, queue, exchange, topic)


def BasicUnsubscribe(channel: pika.adapters.blocking_connection.BlockingChannel,
                     exchange: str, topic: str, queue: str):
    if isinstance(topic, list):
        topics = topic
    else:
        topics = [topic]
    for topic in topics:
        UnbindQueue(channel, queue, exchange, topic)
