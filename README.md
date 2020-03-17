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
import time
import datetime
from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus
from PikaBus.abstractions.AbstractPikaBusSetup import AbstractPikaBusSetup
from PikaBus.PikaBusSetup import PikaBusSetup


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


# Use Pika connection params to set connection details
credentials = pika.PlainCredentials('amqp', 'amqp')
connParams = pika.ConnectionParameters(
            host='localhost',
            port=5672,
            virtual_host='/',
            credentials=credentials)
  
# Create a PikaBusSetup instance with a listener queue, and add the message handler method.
pikaBusSetup: AbstractPikaBusSetup = PikaBusSetup(connParams, listenerQueue='myQueue')
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

# Give it a few seconds for the consumer to receive all sent messages, and then stop all consuming channels
time.sleep(2)
pikaBusSetup.Stop()

# Wait for the consuming tasks to complete safely.
loop = asyncio.get_event_loop()
loop.run_until_complete(asyncio.gather(*consumingTasks))
```

Locate more examples here:
- [./Examples](./Examples)
  - Start the local rabbitmq instance with docker and [DockerBuildManagement](https://github.com/DIPSAS/DockerBuildManagement):
    - pip install DockerBuildManagement 
    - dbm -swarm -start
  - Then run the example:
    - pip install --upgrade PikaBus
    - python ./Examples/basic_example.py

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