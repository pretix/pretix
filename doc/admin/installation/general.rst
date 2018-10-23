.. highlight:: ini

.. spelling:: SQL

General remarks
===============

Requirements
------------
To use pretix, you will need the following things:

* **pretix** and the python packages it depends on

* An **WSGI application server** (we recommend gunicorn)

* A periodic task runner, e.g. ``cron``

* **A database**. This needs to be a SQL-based that is supported by Django. We highly recommend to either
  go for **PostgreSQL** or **MySQL/MariaDB**. If you do not provide one, pretix will run on SQLite, which is useful
  for evaluation and development purposes.

  .. warning:: Do not ever use SQLite in production. It will break.

  .. warning:: We recommend **PostgreSQL**. If you go for MySQL, make sure you run **MySQL 5.7 or newer** or
               **MariaDB 10.2.7 or newer**.

* A **reverse proxy**. pretix needs to deliver some static content to your users (e.g. CSS, images, ...). While pretix
  is capable of doing this, having this handled by a proper web server like **nginx** or **Apache** will be much
  faster. Also, you need a proxying web server in front to provide SSL encryption.

  .. warning:: Do not ever run without SSL in production. Your users deserve encrypted connections and thanks to
               `Let's Encrypt`_ SSL certificates can be obtained for free these days.

* A **redis** server. This will be used for caching, session storage and task queuing.

  .. warning:: pretix can run without redis, however this is only intended for development and should never be
               used in production.

* Optionally: RabbitMQ or memcached. Both of them might provide speedups, but if they are not present,
  redis will take over their job.

.. _Let's Encrypt: https://letsencrypt.org/
