.. _documentation: https://pikabus.readthedocs.org/

PikaBus
========

.. image:: https://readthedocs.org/projects/pikabus/badge/?version=latest
    :target: https://pikabus.readthedocs.org/
    :alt: ReadTheDocs

.. image:: https://travis-ci.com/hansehe/PikaBus.svg?branch=master
    :target: https://travis-ci.com/hansehe/PikaBus
    :alt: Drone CI

.. image:: https://img.shields.io/pypi/v/pikabus.svg
    :target: https://pypi.python.org/pypi/pikabus/
    :alt: Latest Version

.. image:: https://img.shields.io/pypi/pyversions/pikabus.svg
    :target: https://pypi.python.org/pypi/pikabus/

.. image:: https://img.shields.io/pypi/l/pikabus.svg
    :target: https://pypi.python.org/pypi/pikabus/


The `PikaBus <https://github.com/hansehe/PikaBus>`_ library is a wrapper around `pika <https://pypi.org/project/pika/>`_ 
to make it easy to implement the messages, events and command pattern, as described in detail here:

- https://pikabus.readthedocs.io/en/latest/guidelines_amqp.html

Features
--------

- Secure messaging with amqp enabled by default, which includes:
    - Durable and mirrored queues on all nodes.
    - Persistent messages, meaning no messages are lost after a node restart.
    - Delivery confirms with `RabbitMq publisher confirms <https://www.rabbitmq.com/confirms.html>`_.
    - Mandatory delivery turned on by default to guarantee at least once delivery.
- Object oriented API with short and easy-to-use interface.
- Fault-tolerant with auto-reconnect retry logic and state recovery.

Installation
------------

.. code-block:: shell

    pip install PikaBus

Example
-------

.. code-block:: python

    import pika
    import datetime
    from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus
    from PikaBus.PikaBusSetup import PikaBusSetup


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
    pikaBusSetup = PikaBusSetup(connParams,
                                defaultListenerQueue='myQueue',
                                defaultSubscriptions='myTopic')
    pikaBusSetup.AddMessageHandler(MessageHandlerMethod)

    # Start consuming messages from the queue.
    pikaBusSetup.StartAsync()

    # Create a temporary bus to subscribe on topics and send, defer or publish messages.
    bus = pikaBusSetup.CreateBus()
    bus.Subscribe('myTopic')
    payload = {'hello': 'world!', 'reply': True}

    # To send a message means sending a message explicitly to one receiver.
    bus.Send(payload=payload, queue='myQueue')

    # To defer a message means sending a message explicitly to one receiver with some delay before it is processed.
    bus.Defer(payload=payload, delay=datetime.timedelta(seconds=1), queue='myQueue')

    # To publish a message means publishing a message on a topic received by any subscribers of the topic.
    bus.Publish(payload=payload, topic='myTopic')

    input('Hit enter to stop all consuming channels \n\n')
    pikaBusSetup.StopConsumers()


Quick Start
-----------
Clone `PikaBus <https://github.com/hansehe/PikaBus>`_ repo:

.. code-block:: shell

    git clone https://github.com/hansehe/PikaBus.git

Start local `RabbitMq <https://www.rabbitmq.com/>`_ instance with `Docker <https://www.docker.com/products/docker-desktop>`_:

.. code-block:: shell

    docker run -d --name rabbit -e RABBITMQ_DEFAULT_USER=amqp -e RABBITMQ_DEFAULT_PASS=amqp -p 5672:5672 -p 15672:15672 rabbitmq:3-management

Open RabbitMq admin (user=amqp, password=amqp) at:

.. code-block:: shell

    http://localhost:15672/

Then, run the example:

.. code-block:: shell

    pip install PikaBus
    python ./Examples/basic_example.py

Try restarting RabbitMq to notice how PikaBus tolerates downtime:

.. code-block:: shell

    docker stop rabbit
    docker start rabbit

Send or publish more messages to the running PikaBus consumer with:

.. code-block:: shell

    python ./Examples/send_example.py
    python ./Examples/publish_example.py

Contribute
----------

- Issue Tracker: https://github.com/hansehe/PikaBus/issues
- Source Code: https://github.com/hansehe/PikaBus

License
-------

The project is licensed under the MIT license.

Versioning
----------

This software follows `Semantic Versioning <http://semver.org/>`_
