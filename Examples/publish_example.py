import pika
from PikaBus.PikaBusSetup import PikaBusSetup


# Use pika connection params to set connection details
credentials = pika.PlainCredentials('amqp', 'amqp')
connParams = pika.ConnectionParameters(
    host='localhost',
    port=5672,
    virtual_host='/',
    credentials=credentials)

# Create a PikaBusSetup instance without a listener queue
pikaBusSetup = PikaBusSetup(connParams)

# Create a temporary bus to publish messages.
bus = pikaBusSetup.CreateBus()
payload = {'hello': 'world!', 'reply': False}

# To publish a message means publishing a message on a topic received by any subscribers of the topic.
bus.Publish(payload=payload, topic='myTopic')

