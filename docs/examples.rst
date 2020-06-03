========
Examples
========

Start local `RabbitMq <https://www.rabbitmq.com/>`_ instance with `Docker <https://www.docker.com/products/docker-desktop>`_:

.. code-block:: shell

    docker run -d --name rabbit -e RABBITMQ_DEFAULT_USER=amqp -e RABBITMQ_DEFAULT_PASS=amqp -p 5672:5672 -p 15672:15672 rabbitmq:3-management

Open RabbitMq admin (user=amqp, password=amqp) at:

.. code-block:: shell

    http://localhost:15672/

Then, run either of these examples:

Consumer
--------
Following example demonstrates running a simple consumer.

.. literalinclude:: ../Examples/consumer_example.py
   :language: python


Publish Message
---------------
This example demonstrates how to publish a message in a `one-to-many` pattern with at least once guarantee.
The mandatory received flag is turned on by default, so you will get an exception if there are no subscribers on the topic.

.. literalinclude:: ../Examples/publish_example.py
   :language: python

Send Message
------------
This example demonstrates how to send a message in a `one-to-one` pattern with at least once guarantee.
An exception will be thrown if the destination queue doesn't exist. 

.. literalinclude:: ../Examples/send_example.py
   :language: python

Transaction Message
-------------------
This example demonstrates how to send or publish messages in a transaction.
The transaction is automatically handled in the `with` statement.
Basically, all outgoing messages are published at transaction commit.

.. literalinclude:: ../Examples/transaction_example.py
   :language: python

Error Handling
--------------
By default, `PikaBus` implements error handling by forwarding failed messages to a durable queue named `error` 
after 5 retry attemps with backoff policy between each attempt.
Following example demonstrates how it is possible to change the error handler settings, or even replace the error handler.

.. literalinclude:: ../Examples/error_example.py
   :language: python

REST API With Flask & PikaBus
-----------------------------
Following example demonstrates how to combine a REST API with `PikaBus` running as a background job.
`PikaBus` handles restarts and downtime since it's fault-tolerant with auto-reconnect and state recovery.
It is possible to combine `PikaBus` with any other web framework, such as `Tornado <https://www.tornadoweb.org/en/stable/>`_, 
since it's a self-contained background job.

.. literalinclude:: ../Examples/flask_example.py
   :language: python