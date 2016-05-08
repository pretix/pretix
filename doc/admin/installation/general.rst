.. highlight:: ini

General remarks
===============

Requirements
------------
To use pretix, the most minimal setup consists of:

* **pretix** and the python packages it depends on
* An **WSGI application server** (we recommend gunicorn)
* A periodic task runner, e.g. ``cron``

To run pretix, you will need **at least Python 3.4**. We only recommend installations on **Linux**, Windows is not
officially supported (but might work).

Optional requirements
---------------------

pretix is built in a way that makes many of the following requirements optional. However, performance or security might
be very low if you skip some of them, therefore they are only partly optional.

Database
    A good SQL-based database to run on that is supported by Django. We highly recommend to either go for **PostgreSQL**
    or **MySQL/MariaDB**.
    If you do not provide one, pretix will run on SQLite, which is useful for evaluation and development purposes.

    .. warning:: Do not ever use SQLite in production. It will break.

Reverse proxy
    pretix needs to deliver some static content to your users (e.g. CSS, images, ...). While pretix is capable of
    doing this, having this handled by a proper webserver like **nginx** or **Apache** will be much faster. Also, you
    need a proxying web server in front to provide SSL encryption.

    .. warning:: Do not ever run without SSL in production. Your users deserve encrypted connections and thanks to
                 `Let's Encrypt`_ SSL certificates can be obtained for free these days.

Task worker
    When pretix has to do heavy stuff, it is better to offload it into a background process instead of having the
    users connection wait. Therefore pretix provides a background service that can be used to work on those
    longer-running tasks.

    This requires at least Redis (and optionally RabbitMQ).

Redis
    If you provide a redis instance, pretix is able to make use of it in the three following ways:

    * Caching
    * Fast session storage
    * Queuing and result storage for the task worker queue

RabbitMQ
    RabbitMQ can be used as a more advanced queue manager for the task workers, if necessary.

.. _Let's Encrypt: https://letsencrypt.org/
