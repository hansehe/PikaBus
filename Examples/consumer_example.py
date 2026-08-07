import asyncio
from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus
from PikaBus.PikaBusSetup import PikaBusSetup
from PikaBus.PikaErrorHandler import PikaErrorHandler


async def MessageHandlerMethod(**kwargs):
    """
    A message handler method may simply be a method with some **kwargs.
    The **kwargs will be given all incoming pipeline data, the bus and the incoming payload.
    """
    data: dict = kwargs['data']
    bus: AbstractPikaBus = kwargs['bus']
    payload: dict = kwargs['payload']
    print(payload)
    if payload['reply']:
        payload['reply'] = False
        await bus.Reply(payload=payload)


async def Main():
    pikaErrorHandler = PikaErrorHandler(errorQueue='error', maxRetries=1)
    async with PikaBusSetup('amqp://amqp:amqp@localhost:5672/',
                            defaultListenerQueue='myQueue',
                            defaultSubscriptions='myTopic',
                            pikaErrorHandler=pikaErrorHandler) as pikaBusSetup:
        pikaBusSetup.AddMessageHandler(MessageHandlerMethod)
        await pikaBusSetup.StartConsumers()

        # Await the consumers until they stop. SIGINT and SIGTERM stop them gracefully, letting
        # in-flight messages finish and acknowledge first.
        await pikaBusSetup.WaitUntilStopped()


if __name__ == '__main__':
    asyncio.run(Main())
