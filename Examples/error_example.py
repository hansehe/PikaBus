import asyncio
from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus
from PikaBus.PikaBusSetup import PikaBusSetup
from PikaBus.PikaErrorHandler import PikaErrorHandler


async def FailingMessageHandlerMethod(**kwargs):
    """
    A handler that always fails, to show the retry and dead-letter path.

    PikaErrorHandler retries with a backoff by stamping a deferred time on the message. In 2.0 that
    wait actually happens - 1.x republished the message in a tight loop with no delay at all, so a
    one second backoff cost thousands of broker round trips.
    """
    payload: dict = kwargs['payload']
    print(f'Failing message on purpose: {payload}')
    raise Exception('Failing message as I am told!')


async def Main():
    # After maxRetries the message is moved to the error queue, which PikaBus declares and binds.
    pikaErrorHandler = PikaErrorHandler(errorQueue='error', maxRetries=2, delay=1, backoff=2)
    async with PikaBusSetup('amqp://amqp:amqp@localhost:5672/',
                            defaultListenerQueue='myFailingQueue',
                            pikaErrorHandler=pikaErrorHandler) as pikaBusSetup:
        pikaBusSetup.AddMessageHandler(FailingMessageHandlerMethod)
        await pikaBusSetup.Init()
        await pikaBusSetup.StartConsumers()

        async with pikaBusSetup.CreateBus() as bus:
            await bus.Send(payload={'hello': 'world!'}, queue='myFailingQueue')

        print('Watch the message retry with a growing backoff, then land in the error queue.')
        await asyncio.to_thread(input, 'Hit enter to stop all consuming channels \n\n')
        await pikaBusSetup.StopConsumers()


if __name__ == '__main__':
    asyncio.run(Main())
