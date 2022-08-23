import pika
from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus
from PikaBus.PikaBusSetup import PikaBusSetup
from PikaBus.PikaErrorHandler import PikaErrorHandler


def MessageHandlerMethod(**kwargs):
    """
    A message handler method may simply be a method with som **kwargs.
    The **kwargs will be given all incoming pipeline data, the bus and the incoming payload.
    """
    data: dict = kwargs['data']
    bus: AbstractPikaBus = kwargs['bus']
    payload: dict = kwargs['payload']
    print(payload)
    if payload['reply']:
        payload['reply'] = False
        bus.Reply(payload=payload)


# Use pika connection params to set connection details
credentials = pika.PlainCredentials('amqp', 'amqp')
connParams = pika.ConnectionParameters(
    host='localhost',
    port=5672,
    virtual_host='/',
    credentials=credentials)

# Create a PikaBusSetup instance with a listener queue, and add the message handler method.
pikaErrorHandler = PikaErrorHandler(errorQueue='error', maxRetries=1)
pikaBusSetup = PikaBusSetup(connParams,
                            defaultListenerQueue='myQueue',
                            defaultSubscriptions='myTopic',
                            pikaErrorHandler=pikaErrorHandler)
pikaBusSetup.AddMessageHandler(MessageHandlerMethod)

# Start consuming messages from the queue.
pikaBusSetup.StartConsumers()

input('Hit enter to stop all consuming channels \n\n')
pikaBusSetup.StopConsumers()
