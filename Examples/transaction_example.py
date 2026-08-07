import asyncio
import datetime
from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus
from PikaBus.PikaBusSetup import PikaBusSetup


async def Main():
    async with PikaBusSetup('amqp://amqp:amqp@localhost:5672/') as pikaBusSetup:
        await pikaBusSetup.Init(listenerQueue='myQueue', subscriptions='myTopic')

        # Entering the bus starts a transaction. Nothing is published until the block exits cleanly -
        # and if it raises, the buffered messages are discarded instead of partially sent.
        #
        # This is an in-memory outbox, not an AMQP transaction, so the flush itself is not atomic.
        # If some messages publish and others fail, PikaBusTransactionError reports exactly which.
        async with pikaBusSetup.CreateBus(listenerQueue='myQueue') as bus:
            bus: AbstractPikaBus = bus
            payload = {'hello': 'world!', 'reply': False}
            await bus.Send(payload=payload)
            await bus.Defer(payload=payload, delay=datetime.timedelta(seconds=1))
            await bus.Publish(payload=payload, topic='myTopic')
            print('Nothing has been published yet - it is buffered until this block exits.')

        # Drain the queue without starting a consumer. bus.Get() replaces reaching into the raw
        # channel with basic_get(), which no longer exists in an asyncio world.
        async with pikaBusSetup.CreateBus(listenerQueue='myQueue') as bus:
            while True:
                message = await bus.Get(queue='myQueue')
                if message is None:
                    break
                print(f'Got message: {message.body}')


if __name__ == '__main__':
    asyncio.run(Main())
