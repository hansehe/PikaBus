import pika
import json
from PikaBus.PikaBusSetup import PikaBusSetup
from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus


# Use pika connection params to set connection details.
credentials = pika.PlainCredentials('amqp', 'amqp')
connParams = pika.ConnectionParameters(
    host='localhost',
    port=5672,
    virtual_host='/',
    credentials=credentials)

# Create a PikaBusSetup instance without a listener queue.
pikaBusSetup = PikaBusSetup(connParams)

# Run Init to create default listener queue, exchanges and subscriptions.
pikaBusSetup.Init(listenerQueue='myQueue', subscriptions='myQueue')

# Create a temporary bus transaction using the `with` statement
# to transmit all outgoing messages at the end of the transaction.
with pikaBusSetup.CreateBus() as bus:
    bus: AbstractPikaBus = bus
    payload = {'hello': 'world!', 'reply': False}
    bus.Send(payload=payload, queue='myQueue')
    bus.Publish(payload=payload, topic='myQueue')

# Fetch and print all messages from the queue synchronously.
with pikaBusSetup.CreateBus() as bus:
    bus: AbstractPikaBus = bus
    message = bus.channel.basic_get('myQueue', auto_ack=True)
    while message[0] is not None:
        print(json.loads(message[2]))
        message = bus.channel.basic_get('myQueue', auto_ack=True)
