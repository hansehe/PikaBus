import pika
import pika.exceptions
import time


def CreateDurableQueue(channel: pika.adapters.blocking_connection.BlockingChannel, queue: str):
    channel.queue_declare(queue, durable=True, passive=False)


def CreateExchange(channel: pika.adapters.blocking_connection.BlockingChannel, exchange: str,
                   exchangeType: str = 'direct'):
    channel.exchange_declare(exchange, exchange_type=exchangeType, passive=False, durable=True)


def BindQueue(channel: pika.adapters.blocking_connection.BlockingChannel, queue: str, exchange: str, topic: str):
    channel.queue_bind(queue, exchange, routing_key=topic)


def AssertDurableQueueExists(connection: pika.BlockingConnection, queue: str, retries: int = 0):
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
    raise Exception(f"Queue {queue} does not exist!")


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
              exchangeType: str = 'direct'):
    CreateExchange(channel, exchange, exchangeType=exchangeType)
    BindQueue(channel, queue=destination, exchange=exchange, topic=destination)
    channel.basic_publish(exchange, destination, body, properties=properties)


def BasicPublish(channel: pika.adapters.blocking_connection.BlockingChannel,
                 exchange: str, topic: str, body: bytes,
                 properties: pika.spec.BasicProperties = None,
                 exchangeType: str = 'topic'):
    CreateExchange(channel, exchange, exchangeType=exchangeType)
    channel.basic_publish(exchange, topic, body, properties=properties)
