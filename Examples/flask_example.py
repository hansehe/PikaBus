import asyncio
import pika
import logging
import atexit
from flask import Flask
from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus
from PikaBus.abstractions.AbstractPikaBusSetup import AbstractPikaBusSetup
from PikaBus.PikaBusSetup import PikaBusSetup

# Prequisites
# - pip install flask

logging.basicConfig(format=f'[%(levelname)s] %(name)s - %(message)s', level='WARNING')
log = logging.getLogger(__name__)


def SafeStopAmqpConsumers(consumingTasks: list, pikaBusSetup: AbstractPikaBusSetup):
    log.warning('Stopping consumers')
    pikaBusSetup.Stop()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(asyncio.gather(*consumingTasks))
    log.warning('Stopped consumers and exiting')


def MessageHandlerMethod(**kwargs):
    """
    A message handler method may simply be a method with som **kwargs.
    The **kwargs will be given all incoming pipeline data, the bus and the incoming payload.
    """
    data: dict = kwargs['data']
    bus: AbstractPikaBus = kwargs['bus']
    payload: dict = kwargs['payload']
    print(f'Received message: {payload}')

# Use pika connection params to set connection details
credentials = pika.PlainCredentials('amqp', 'amqp')
connParams = pika.ConnectionParameters(
    host='localhost',
    port=5672,
    virtual_host='/',
    credentials=credentials)

# Create a PikaBusSetup instance with a listener queue, and add the message handler method.
pikaBusSetup: AbstractPikaBusSetup = PikaBusSetup(connParams,
                                                  defaultListenerQueue='myQueue',
                                                  defaultSubscriptions='myTopic')
pikaBusSetup.AddMessageHandler(MessageHandlerMethod)

# Start consuming messages from the queue and register the exit function.
consumingTasks = pikaBusSetup.StartAsync()
atexit.register(SafeStopAmqpConsumers, consumingTasks, pikaBusSetup)

# Create a flask app
app = Flask(__name__)

# Create an api route that simply publishes a message
@app.route('/')
def Publish():
    bus: AbstractPikaBus = pikaBusSetup.CreateBus()
    payload = {'hello': 'world!'}
    bus.Publish(payload=payload, topic='myTopic')
    return 'Payload published :D'

# Run flask app on http://localhost:5005/
app.run(debug=True, host='0.0.0.0', port=5005)