import asyncio
import datetime
from PikaBus.PikaBusSetup import PikaBusSetup


async def Main():
    async with PikaBusSetup('amqp://amqp:amqp@localhost:5672/',
                            defaultListenerQueue='myQueue') as pikaBusSetup:
        # Init() creates the queue and binds it to the direct exchange, which is what makes it
        # addressable with Send(). PikaBus 1.x instead bound the destination on every single send, so
        # a hand-created queue happened to work; 2.0 needs the queue to have been initialised.
        # A consumer started with StartConsumers() does this for you.
        await pikaBusSetup.Init()

        payload = {'hello': 'world!', 'reply': True}

        # Entering the bus starts a transaction, so these only buffer the messages - nothing reaches
        # the broker until the block exits, which is also where a failure would surface.
        async with pikaBusSetup.CreateBus() as bus:
            # Sending is mandatory by default, so the commit raises
            # aio_pika.exceptions.DeliveryError (wrapped in PikaBusTransactionError) if the
            # destination queue does not exist or is not bound to the direct exchange.
            await bus.Send(payload=payload, queue='myQueue')
            await bus.Defer(payload=payload, delay=datetime.timedelta(seconds=10), queue='myQueue')

        print('Payload sent :D')
        print('Payload deferred 10 seconds :D')


if __name__ == '__main__':
    asyncio.run(Main())
