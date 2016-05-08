.. highlight:: ini

Installation
============

Requirements
------------
To use pretix, the most minimal setup consists of:

* **pretix** and the python packages it depends on
* An **WSGI application server** (we recommend gunicorn)
* A periodic task runner, e.g. ``cron``

You get those two bundled in the ``pretix/standalone`` docker image.

If you want to set them up manually, you can also get pretix from GitHub or wait for us to set up proper
``pip`` packages and set up a simple gunicorn instance pointing to the ``pretix.wsgi`` endpoint.

To run pretix, you will need **at least Python 3.4**.

You can get the direct dependencies by doing a ``pip install -r requirements.txt`` in the pretix source
directory. We'll provide detailled documentation on this as soon as pretix will be officially released.

If you have real users on your system you'll **really** want to use

* A database (MySQL or PostgreSQL)
* A reverse proxy web server (nginx or Apache)

Optionally, you can speed up pretix by adding

* A memcached instance
* A redis database
* A celery background task-queue (using redis or RabbitMQ for messaging)

Depending on your choice at this options, you should also install ``pip install -r requirements/<service>.txt``
where ``<service>`` is one of ``celery``, ``memcached``, ``mysql``, ``postgres`` or ``redis``.

If you want to use one of the payment providers shipping with pretix, you should also install
``pip install -r requirements/<plugin>.txt`` where ``<plugin>`` is one of ``banktransfer``, ``paypal`` or ``stripe``.

We will provide a step-by-step tutorial with the first stable release, but all configuration
already :ref:`is documented <config>`.

Set up a cronjob
----------------

You need to set up a cronjob that runs the management command ``runperiodic``. The exact interval is not important
but should be something between every minute and every hour. You could for example configure cron like this::

    15,45 * * * * python3 /path/to/pretix/manage.py runperiodic