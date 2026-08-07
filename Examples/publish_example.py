import asyncio
from PikaBus.PikaBusSetup import PikaBusSetup


async def Main():
    # A PikaBusSetup with no listener queue acts purely as a publisher.
    async with PikaBusSetup('amqp://amqp:amqp@localhost:5672/') as pikaBusSetup:
        payload = {'hello': 'world!', 'reply': True}

        # Entering the bus starts a transaction, so Publish only buffers the message - nothing
        # reaches the broker until the block exits. Report success after that, not inside.
        async with pikaBusSetup.CreateBus() as bus:
            # Publishing is mandatory by default, so the commit below raises
            # aio_pika.exceptions.DeliveryError (wrapped in PikaBusTransactionError) if nobody
            # is subscribed to the topic. Run basic_example first so there is a subscriber.
            await bus.Publish(payload=payload, topic='myTopic')

        print('Payload published :D')


if __name__ == '__main__':
    asyncio.run(Main())
