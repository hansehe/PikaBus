import pika
import datetime
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

# Create a temporary bus to send messages.
bus = pikaBusSetup.CreateBus()
payload = {'hello': 'world!', 'reply': False}

# To send a message means sending a message explicitly to one receiver. 
# The sending will fail if the destination queue `myQueue` doesn't exist.
# Create `myQueue` in the RabbitMq admin portal at http://localhost:15672 if it doesn't exist (user=amqp, password=amqp)
bus.Send(payload=payload, queue='myQueue')

# To defer a message means sending a message explicitly to one receiver with some delay before it is processed.
bus.Defer(payload=payload, delay=datetime.timedelta(seconds=10), queue='myQueue')
