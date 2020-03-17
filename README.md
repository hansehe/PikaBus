# PikaBus

[![PyPI version](https://badge.fury.io/py/PikaBus.svg)](https://badge.fury.io/py/PikaBus)
[![Build Status](https://travis-ci.com/hansehe/PikaBus.svg?branch=master)](https://travis-ci.com/hansehe/PikaBus)
[![MIT license](http://img.shields.io/badge/license-MIT-brightgreen.svg)](http://opensource.org/licenses/MIT)

The [PikaBus](https://github.com/hansehe/PikaBus) library is a wrapper around [pika](https://pypi.org/project/pika/) 
to make it easy to implement the messages, events and command pattern, as described in detail here:
- https://docs.particular.net/nservicebus/messaging/messages-events-commands


## Install Or Upgrade
- pip install --upgrade PikaBus

## Prerequisites
- python3x

## Example
```python
import asyncio
import pika
import logging
import datetime
from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus
from PikaBus.abstractions.AbstractPikaBusSetup import AbstractPikaBusSetup
from PikaBus.PikaBusSetup import PikaBusSetup

logging.basicConfig(format=f'[%(levelname)s] %(name)s - %(message)s', level='WARNING')


def messageHandlerMethod(**kwargs):
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
pikaBusSetup: AbstractPikaBusSetup = PikaBusSetup(connParams, defaultListenerQueue='myQueue')
pikaBusSetup.AddMessageHandler(messageHandlerMethod)

# Start consuming messages from the queue.
consumingTasks = pikaBusSetup.StartAsync()

# Create a temporary bus to subscribe on topics and send, defer or publish messages.
bus: AbstractPikaBus = pikaBusSetup.CreateBus()
bus.Subscribe('myTopic')
payload = {'hello': 'world!', 'reply': True}

# To send a message means sending a message explicitly to one receiver.
bus.Send(payload=payload, queue='myQueue')

# To defer a message means sending a message explicitly to one receiver with some delay before it is processed.
bus.Defer(payload=payload, delay=datetime.timedelta(seconds=1), queue='myQueue')

# To publish a message means publishing a message on a topic to any subscribers of the topic.
bus.Publish(payload=payload, topic='myTopic')

input('Hit enter to stop all consuming channels \n\n')
pikaBusSetup.Stop()

# Wait for the consuming tasks to complete safely.
loop = asyncio.get_event_loop()
loop.run_until_complete(asyncio.gather(*consumingTasks))
```

### Clone example and run it:
- https://github.com/hansehe/PikaBus/blob/master/Examples/basic_example.py
- clone repo: 
  - `git clone https://github.com/hansehe/PikaBus.git`
- Start local [RabbitMq](https://www.rabbitmq.com/) instance with [Docker](https://www.docker.com/products/docker-desktop) and [DockerBuildManagement](https://github.com/DIPSAS/DockerBuildManagement):
  - `pip install DockerBuildManagement` 
  - `dbm -swarm -start`
  - Open RabbitMq admin (user=amqp,password=amqp) at:
    - http://localhost:15672/ 
- Then run the example:
  - `pip install --upgrade PikaBus`
  - `python ./Examples/basic_example.py`
  - Try restarting RabbitMq to notice how PikaBus tolerates downtime:
    - `dbm -swarm -restart`
  - Send more messages to the running PikaBus consumer with:
    - `python ./Examples/send_example.py`

## Development

### Dependencies:
  - `pip install twine`
  - `pip install wheel`
  - `pip install -r requirements.txt`

### Publish New Version.
1. Configure [setup.py](./setup.py) with new version.
2. Package: `python setup.py bdist_wheel`
3. Publish: `twine upload dist/*`
4. Or with dbm:
   - pip install DockerBuildManagement 
   - dbm -build -publish 

### Run Unit Tests
- pip install DockerBuildManagement 
- dbm -test