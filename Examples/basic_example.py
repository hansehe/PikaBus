import asyncio
import pika
import time
from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus
from PikaBus.PikaBusSetup import PikaBusSetup

def messageHandlerMethod(**kwargs):
  """
  A message handler method may simply be a method with som **kwargs.
  The **kwargs will be given all incoming pipeline data, the bus and the incoming payload as a dictionary.
  """
  data: dict = kwargs['data']
  bus: AbstractPikaBus = kwargs['bus']
  payload: dict = kwargs['payload']
  print(payload)

# Use Pika connection params to set connection details
credentials = pika.PlainCredentials('amqp', 'amqp')
connParams = pika.ConnectionParameters(
        host='localhost',
        port=5672,
        virtual_host='/',
        credentials=credentials)
  
# Create a PikaBusSetup instance with a listener queue, and add the message handler method.
pikaBusSetup = PikaBusSetup(connParams, listenerQueue='myQueue')
pikaBusSetup.AddMessageHandler(messageHandlerMethod)

# Start consuming messages from the queue.
consumingTask = pikaBusSetup.StartAsync()

# Create a temporary bus to subscribe on topics and send or publish messages.
bus: AbstractPikaBus = pikaBusSetup.CreateBus()
bus.Subscribe('myTopic')
payload = {'hello': 'world!'}
bus.Send(payload=payload, queue='myQueue')
bus.Publish(payload=payload, topic='myTopic')

# Give it a few seconds for the consumer to receive all sent messages, and then stop all consuming channels
time.sleep(2)
pikaBusSetup.Stop()

# Wait for the consuming task to complete safely.
loop = asyncio.get_event_loop()
loop.run_until_complete(consumingTask)