.. _documentation: https://pikabus.readthedocs.org/

PikaBus
========

.. image:: https://readthedocs.org/projects/pikabus/badge/?version=latest
    :target: https://pikabus.readthedocs.org/
    :alt: ReadTheDocs

.. image:: https://github.com/hansehe/PikaBus/actions/workflows/ci.yml/badge.svg?branch=master
    :target: https://github.com/hansehe/PikaBus/actions/workflows/ci.yml
    :alt: CI

.. image:: https://img.shields.io/pypi/v/pikabus.svg
    :target: https://pypi.python.org/pypi/pikabus/
    :alt: Latest Version

.. image:: https://img.shields.io/pypi/pyversions/pikabus.svg
    :target: https://pypi.python.org/pypi/pikabus/

.. image:: https://img.shields.io/pypi/l/pikabus.svg
    :target: https://pypi.python.org/pypi/pikabus/


The `PikaBus <https://github.com/hansehe/PikaBus>`_ library is an asyncio message bus built on
`aio-pika <https://pypi.org/project/aio-pika/>`_, making it easy to implement the messages, events and
command pattern, as described in detail here:

- https://pikabus.readthedocs.io/en/latest/guidelines_amqp.html

.. note::
    **PikaBus 2.0 is asyncio-only and is a breaking change.** 1.x was built on
    `pika <https://pypi.org/project/pika/>`_ and ran one blocking thread per consumer. See the
    *Migrating from 1.x* section below. 1.x remains available for Python 3.6 - 3.10.

Features
--------

- Secure messaging with amqp enabled by default, which includes:
    - Durable queues and persistent messages, meaning no messages are lost after a node restart.
    - Delivery confirms with `RabbitMq publisher confirms <https://www.rabbitmq.com/confirms.html>`_.
    - Mandatory delivery turned on by default, so an unroutable message raises rather than vanishing.
- Object oriented API with short and easy-to-use interface.
- Fault-tolerant, with automatic reconnection and consumer recovery handled by aio-pika's robust
  connection, plus a retry policy with real exponential backoff and jitter.
- Genuinely asynchronous: no threads, one connection multiplexed over a channel per consumer.
- Message handlers may be ``async def`` or plain ``def``.
- Graceful shutdown on SIGINT/SIGTERM, letting in-flight messages finish and acknowledge.

Installation
------------

.. code-block:: shell

    pip install PikaBus

or with `uv <https://docs.astral.sh/uv/>`_:

.. code-block:: shell

    uv add PikaBus

Requires Python 3.11 or newer.

Example
-------

.. code-block:: python

    import asyncio
    import datetime
    from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus
    from PikaBus.PikaBusSetup import PikaBusSetup


    async def MessageHandlerMethod(**kwargs):
        """
        A message handler method may simply be a method with some **kwargs.
        The **kwargs will be given all incoming pipeline data, the bus and the incoming payload.

        Make it `async def` if it publishes anything - the bus methods are coroutines.
        """
        data: dict = kwargs['data']
        bus: AbstractPikaBus = kwargs['bus']
        payload: dict = kwargs['payload']
        print(payload)
        if payload['reply']:
            payload['reply'] = False
            await bus.Reply(payload=payload)


    async def Main():
        # Connection details are an amqp url. Alternatively pass host/port/login/password kwargs.
        async with PikaBusSetup('amqp://amqp:amqp@localhost:5672/',
                                defaultListenerQueue='myQueue',
                                defaultSubscriptions='myTopic') as pikaBusSetup:
            pikaBusSetup.AddMessageHandler(MessageHandlerMethod)

            # Start consuming messages from the queue.
            # Returns once the consumers are actually consuming, so the sends below cannot race it.
            await pikaBusSetup.StartConsumers()

            # Create a temporary bus to subscribe on topics and send, defer or publish messages.
            async with pikaBusSetup.CreateBus() as bus:
                await bus.Subscribe('myTopic')
                payload = {'hello': 'world!', 'reply': True}

                # To send a message means sending a message explicitly to one receiver.
                await bus.Send(payload=payload, queue='myQueue')

                # To defer a message means sending a message explicitly to one receiver with some
                # delay before it is processed.
                await bus.Defer(payload=payload, delay=datetime.timedelta(seconds=1), queue='myQueue')

                # To publish a message means publishing a message on a topic received by any
                # subscribers of the topic.
                await bus.Publish(payload=payload, topic='myTopic')

            await asyncio.to_thread(input, 'Hit enter to stop all consuming channels \n\n')
            await pikaBusSetup.StopConsumers()


    if __name__ == '__main__':
        asyncio.run(Main())


Quick Start
-----------
Clone `PikaBus <https://github.com/hansehe/PikaBus>`_ repo:

.. code-block:: shell

    git clone https://github.com/hansehe/PikaBus.git

Start local `RabbitMq <https://www.rabbitmq.com/>`_ instance with `Docker <https://www.docker.com/products/docker-desktop>`_:

.. code-block:: shell

    docker run -d --name rabbit -e RABBITMQ_DEFAULT_USER=amqp -e RABBITMQ_DEFAULT_PASS=amqp -p 5672:5672 -p 15672:15672 rabbitmq:4-management

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

Migrating from 1.x
------------------

**Python 3.11+ is required.** aio-pika 10.x sets that floor. If you are on Python 3.6 - 3.10, stay
on PikaBus 1.x.

**Connection parameters became a url.** ``pika`` is no longer a dependency, so
``pika.ConnectionParameters`` is gone:

.. code-block:: python

    # 1.x
    credentials = pika.PlainCredentials('amqp', 'amqp')
    connParams = pika.ConnectionParameters(host='localhost', port=5672,
                                           virtual_host='/', credentials=credentials)
    pikaBusSetup = PikaBusSetup(connParams, defaultListenerQueue='myQueue')

    # 2.0
    pikaBusSetup = PikaBusSetup('amqp://amqp:amqp@localhost:5672/', defaultListenerQueue='myQueue')
    # or
    pikaBusSetup = PikaBusSetup(host='localhost', port=5672, virtualHost='/',
                                login='amqp', password='amqp', defaultListenerQueue='myQueue')

**Await everything that touches the broker**, and swap ``with`` for ``async with``:

.. code-block:: python

    # 1.x                              # 2.0
    pikaBusSetup.Init()                 await pikaBusSetup.Init()
    pikaBusSetup.StartConsumers()       await pikaBusSetup.StartConsumers()
    pikaBusSetup.StopConsumers()        await pikaBusSetup.StopConsumers()
    pikaBusSetup.LoopForever()          await pikaBusSetup.WaitUntilStopped()
    with pikaBusSetup.CreateBus() as b: async with pikaBusSetup.CreateBus() as b:
    bus.Send(...)                       await bus.Send(...)

Using ``with`` on a bus raises a ``TypeError`` telling you to use ``async with``.

**Handlers that publish must be** ``async def``. A plain ``def`` handler still works, but the bus
methods are coroutines, so calling one without awaiting it silently does nothing. A synchronous
handler also runs on the event loop and must not block.

**Read incoming headers from the new key.** aio-pika has no frame objects:

.. code-block:: python

    # 1.x
    headers = data[PikaConstants.DATA_KEY_INCOMING_MESSAGE][PikaConstants.DATA_KEY_HEADER_FRAME].headers
    # 2.0
    headers = data[PikaConstants.DATA_KEY_INCOMING_MESSAGE][PikaConstants.DATA_KEY_HEADERS]
    # the raw aio-pika message is also available
    message = data[PikaConstants.DATA_KEY_INCOMING_MESSAGE][PikaConstants.DATA_KEY_MESSAGE]

``DATA_KEY_HEADER_FRAME`` still resolves to a shim exposing ``.headers`` and ``.delivery_tag``, but it
emits a ``DeprecationWarning`` and is removed in 2.1.

Behaviour changes
~~~~~~~~~~~~~~~~~

- **Deferred messages now really wait.** 1.x republished a not-yet-due message and acknowledged it
  immediately, with no delay - so a ten second ``Defer`` cost thousands of broker round trips, and
  every error-handler retry backoff did the same. 2.0 holds the message unacknowledged instead, in
  hops of at most ``maxDeferredSleep`` (5 minutes by default). Nothing is lost if the process dies
  mid-wait, since the message was never acknowledged. Note a waiting message occupies one prefetch
  slot.
- **``defaultPrefetchCount`` is 10, not 0.** In 1.x, 0 meant *unlimited*: one consumer would pull an
  entire backlog into memory. Raise it for throughput.
- **``retryParams`` are honoured.** 1.x read only ``tries`` and reconnected in a tight loop with no
  delay. ``delay``, ``max_delay``, ``backoff`` and ``jitter`` now work.
- **A poison message that also breaks the error handler is requeued once, then rejected**, rather
  than requeued forever. It is discarded unless the queue declares ``x-dead-letter-exchange``.
- **Sending no longer binds the destination on every message.** Queues are bound to the direct
  exchange when they are declared, and other destinations are bound once per channel. A ``Send`` to
  a queue PikaBus never initialised now raises ``aio_pika.exceptions.DeliveryError`` instead of the
  old ``Queue X does not exist!``. Inside a transaction the failure surfaces at
  ``CommitTransaction()`` rather than at ``Send()``.
- **``HealthCheck()`` can now return ``False``.** In 1.x it returned ``True`` even with no consumers
  running at all. It now verifies the consumer is registered and its task is alive. Treat it as a
  readiness probe - it is briefly ``False`` during a reconnect - or pass ``allowReconnecting=True``
  for liveness.
- **``StopConsumers()`` no longer poisons the instance.** In 1.x it shut down the shared thread pool,
  so ``StartConsumers()`` could never work again.
- **``ha-mode: all`` was dropped from the default queue arguments, because it never did anything.**
  Classic queue mirroring was configured with policies, not queue arguments, and was removed entirely
  in RabbitMq 4.0. If you believed those queues were mirrored, they were not. For real redundancy use
  ``defaultListenerQueueSettings={'arguments': {'x-queue-type': 'quorum'}}`` - but only on a queue
  that does not exist yet, since ``x-queue-type`` is checked when redeclaring.
- **The published AMQP ``timestamp`` property is now correct.** 1.x ran a UTC time through
  ``time.mktime()``, which reads it as local time, so the timestamp was off by the machine's UTC
  offset and by a different amount either side of a DST change.
- **Header timestamps are ISO 8601.** ``PikaBus.TimeSent`` and ``PikaBus.DeferredTime`` are now
  written as e.g. ``2026-08-07T16:32:19.123456+00:00`` instead of 1.x's ``08/07/2026 16:32:19`` - an
  ambiguous US-style format with no timezone and only second resolution. ``StringToDatetime`` returns
  a timezone-aware datetime, and ``Defer()`` now accepts sub-second delays. **Reading accepts both
  formats**, so this is safe for a rolling upgrade - see below. Pass
  ``PikaProperties(timeFormat='%m/%d/%Y %H:%M:%S')`` if you need the old strings written on the wire.
- **``messsageTypeHeaderKey`` is spelled ``messageTypeHeaderKey``.** The old name still works with a
  ``DeprecationWarning``. The wire header was never misspelled.
- **Concurrency is opt-in.** Each consumer processes messages serially by default, as in 1.x. Set
  ``defaultConcurrency`` above 1 only if your handlers are safe to run concurrently; doing so gives up
  per-queue ordering.

Upgrading a running deployment
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The timestamp format changed, but ``StringToDatetime`` parses **both** the ISO 8601 and the 1.x
format regardless of which one is configured for writing. So a 2.0 consumer reads messages a 1.x
publisher is still producing, and messages already sitting in a queue are consumed normally. **No
drain and no staged rollout are required** - deploy in any order.

The first time a fallback parse happens, PikaBus logs one warning per format:

.. code-block:: text

    Parsed an incoming timestamp as '%m/%d/%Y %H:%M:%S' after ISO 8601 failed.
    Another PikaBus version is still publishing to this queue.

That is your signal that some publisher has not been upgraded yet. It is informational, not an error -
the message is handled normally. It appears once per process, not once per message.

The one direction that cannot work is a **1.x consumer reading a 2.0 message**, since 1.x has no
fallback and its released code cannot be changed. If you must run 1.x consumers alongside 2.0
publishers for a while, pin the 2.0 publishers to the old format with
``PikaProperties(timeFormat='%m/%d/%Y %H:%M:%S')`` and drop that argument once the 1.x consumers are
gone. Otherwise, **upgrade consumers before publishers**.

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
