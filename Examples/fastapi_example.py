import contextlib
import logging

import uvicorn
from fastapi import FastAPI

from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus
from PikaBus.PikaBusSetup import PikaBusSetup

# Requirements
# - pip install fastapi uvicorn
#
# This replaces the Flask example from PikaBus 1.x. Flask is a synchronous WSGI framework, so hosting
# an asyncio consumer alongside it needs a bridging thread. FastAPI runs on the same event loop as the
# bus, and its lifespan hook is exactly the right place to start and stop consumers.

logging.basicConfig(format=f'[%(levelname)s] %(name)s - %(message)s', level='WARNING')
log = logging.getLogger(__name__)

pikaBusSetup = PikaBusSetup('amqp://amqp:amqp@localhost:5672/',
                            defaultListenerQueue='myFastApiQueue',
                            defaultSubscriptions='myFastApiTopic')


async def MessageHandlerMethod(**kwargs):
    """
    A message handler method may simply be a method with some **kwargs.
    The **kwargs will be given all incoming pipeline data, the bus and the incoming payload.
    """
    data: dict = kwargs['data']
    bus: AbstractPikaBus = kwargs['bus']
    payload: dict = kwargs['payload']
    print(f'Received message: {payload}')


@contextlib.asynccontextmanager
async def Lifespan(app: FastAPI):
    # Consumers share the web server's event loop - no threads, no executor.
    pikaBusSetup.AddMessageHandler(MessageHandlerMethod)
    await pikaBusSetup.StartConsumers()
    yield
    # In-flight messages are given time to finish and acknowledge before shutdown.
    await pikaBusSetup.Close()


app = FastAPI(lifespan=Lifespan)


@app.get('/')
async def Publish():
    async with pikaBusSetup.CreateBus() as bus:
        bus: AbstractPikaBus = bus
        payload = {'hello': 'world!', 'reply': True}
        await bus.Publish(payload=payload, topic='myFastApiTopic')
        return 'Payload published :D'


@app.get('/health')
async def Health():
    # Readiness: False for a moment while the connection is recovering.
    # Pass allowReconnecting=True for a liveness probe that should tolerate a reconnect.
    healthy = await pikaBusSetup.HealthCheck()
    return {'healthy': healthy}


if __name__ == '__main__':
    # Run the app on http://localhost:5005/
    uvicorn.run(app, host='0.0.0.0', port=5005)
