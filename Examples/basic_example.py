import asyncio
import datetime
from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus
from PikaBus.PikaBusSetup import PikaBusSetup


async def MessageHandlerMethod(**kwargs):
    """
    A message handler method may simply be a method with some **kwargs.
    The **kwargs will be given all incoming pipeline data, the bus and the incoming payload.

    Make it `async def` if it publishes anything - the bus methods are coroutines, so calling one
    from a plain `def` handler would create a coroutine that is never awaited and silently do nothing.
    """
    data: dict = kwargs['data']
    bus: AbstractPikaBus = kwargs['bus']
    payload: dict = kwargs['payload']
    print(payload)
    if payload['reply']:
        payload['reply'] = False
        await bus.Reply(payload=payload)


async def Main():
    # Connection details are an amqp url since 2.0.
    async with PikaBusSetup('amqp://amqp:amqp@localhost:5672/',
                            defaultListenerQueue='myQueue',
                            defaultSubscriptions='myTopic') as pikaBusSetup:
        pikaBusSetup.AddMessageHandler(MessageHandlerMethod)

        # Start consuming messages from the queue. Returns once the consumers are actually consuming.
        await pikaBusSetup.StartConsumers()

        # Create a temporary bus to subscribe on topics and send, defer or publish messages.
        async with pikaBusSetup.CreateBus() as bus:
            await bus.Subscribe('myTopic')
            payload = {'hello': 'world!', 'reply': True}

            # To send a message means sending a message explicitly to one receiver.
            await bus.Send(payload=payload, queue='myQueue')

            # To defer a message means sending a message explicitly to one receiver with some delay
            # before it is processed.
            await bus.Defer(payload=payload, delay=datetime.timedelta(seconds=1), queue='myQueue')

            # To publish a message means publishing a message on a topic received by any subscribers
            # of the topic.
            await bus.Publish(payload=payload, topic='myTopic')

        await asyncio.to_thread(input, 'Hit enter to stop all consuming channels \n\n')
        await pikaBusSetup.StopConsumers()


if __name__ == '__main__':
    asyncio.run(Main())
