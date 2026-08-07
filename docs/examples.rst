========
Examples
========

Start local `RabbitMq <https://www.rabbitmq.com/>`_ instance with `Docker <https://www.docker.com/products/docker-desktop>`_:

.. code-block:: shell

    docker run -d --name rabbit -e RABBITMQ_DEFAULT_USER=amqp -e RABBITMQ_DEFAULT_PASS=amqp -p 5672:5672 -p 15672:15672 rabbitmq:4-management

Open RabbitMq admin (user=amqp, password=amqp) at:

.. code-block:: shell

    http://localhost:15672/

Then, run either of these examples:

Basic
-----
Following example demonstrates the whole loop - a consumer plus sending, deferring and publishing.

.. literalinclude:: ../Examples/basic_example.py
   :language: python

Consumer
--------
Following example demonstrates running a simple consumer.
``WaitUntilStopped()`` awaits the consumers, and SIGINT or SIGTERM stops them gracefully so
in-flight messages can finish and acknowledge first.

.. literalinclude:: ../Examples/consumer_example.py
   :language: python


Publish Message
---------------
This example demonstrates how to publish a message in a `one-to-many` pattern with at least once guarantee.
The mandatory delivery flag is turned on by default, so you will get an
``aio_pika.exceptions.DeliveryError`` if there are no subscribers on the topic.

.. literalinclude:: ../Examples/publish_example.py
   :language: python

Send Message
------------
This example demonstrates how to send a message in a `one-to-one` pattern with at least once guarantee.
An ``aio_pika.exceptions.DeliveryError`` is raised if the destination queue does not exist, or exists
but was not bound to the direct exchange by ``Init()`` or ``StartConsumers()``.

.. literalinclude:: ../Examples/send_example.py
   :language: python

Transaction Handling
--------------------
This example demonstrates how to send or publish messages in a transaction.
The transaction is automatically handled in the ``async with`` statement:
all outgoing messages are published at transaction commit, and discarded if the block raises.

This is an in-memory outbox rather than an AMQP transaction, so the commit itself is not atomic.
If some messages publish and others fail, ``PikaBusTransactionError`` reports exactly which did which.

.. literalinclude:: ../Examples/transaction_example.py
   :language: python

Error Handling
--------------
By default, `PikaBus` implements error handling by forwarding failed messages to a durable queue named `error`
after 5 retry attempts with a backoff policy between each attempt.
Following example demonstrates how it is possible to change the error handler settings, or even replace the error handler.

.. literalinclude:: ../Examples/error_example.py
   :language: python

REST API With FastAPI & PikaBus
-------------------------------
Following example demonstrates how to combine a REST API with `PikaBus` consumers running on the same
event loop. `PikaBus` handles restarts and downtime since it's fault-tolerant with auto-reconnect and
state recovery. FastAPI's ``lifespan`` hook is the natural place to start and stop consumers.

It is possible to combine `PikaBus` with any asyncio web framework, such as
`aiohttp <https://docs.aiohttp.org/>`_. Note that a synchronous WSGI framework like Flask - used by
this example before PikaBus 2.0 - needs a separate thread to host the event loop.

.. literalinclude:: ../Examples/fastapi_example.py
   :language: python
