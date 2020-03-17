import pika
import logging
from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus
from PikaBus.abstractions.AbstractPikaBusSetup import AbstractPikaBusSetup
from PikaBus.PikaBusSetup import PikaBusSetup

logging.basicConfig(format=f'[%(levelname)s] %(name)s - %(message)s', level='WARNING')


# Use pika connection params to set connection details
credentials = pika.PlainCredentials('amqp', 'amqp')
connParams = pika.ConnectionParameters(
    host='localhost',
    port=5672,
    virtual_host='/',
    credentials=credentials)

# Create a PikaBusSetup instance without a listener queue
pikaBusSetup: AbstractPikaBusSetup = PikaBusSetup(connParams)

# Create a temporary bus to publish messages.
bus: AbstractPikaBus = pikaBusSetup.CreateBus()
payload = {'hello': 'world!', 'reply': False}

# To publish a message means publishing a message on a topic received by any subscribers of the topic.
bus.Publish(payload=payload, topic='myTopic')

