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
---------------

.. literalinclude:: ../Examples/consumer_example.py
   :language: python


Publish Message
---------------

.. literalinclude:: ../Examples/publish_example.py
   :language: python

Send Message
---------------

.. literalinclude:: ../Examples/send_example.py
   :language: python


Error Handling
---------------

.. literalinclude:: ../Examples/error_example.py
   :language: python

REST API With Flask & PikaBus
---------------

.. literalinclude:: ../Examples/flask_example.py
   :language: python