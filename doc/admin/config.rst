.. highlight:: ini

.. _`config`:

.. spelling:: Galera

Configuration file
==================

Pretix reads its configuration from a configuration file. It tries to find this file
at the following locations. It will try to read the file from the specified paths in
the following order. The file that is found *last* will override the settings from
the files found before.

1. ``PREFIX_CONFIG_FILE`` environment variable
2. ``/etc/pretix/pretix.cfg``
3. ``~/.pretix.cfg``
4. ``pretix.cfg`` in the current working directory

The file is expected to be in the INI format as specified in the `Python documentation`_.

The config file may contain the following sections (all settings are optional and have
default values). We suggest that you start from the examples given in one of the
installation tutorials.

pretix settings
---------------

Example::

    [pretix]
    instance_name=pretix.de
    url=http://localhost
    currency=EUR
    datadir=/data
    plugins_default=pretix.plugins.sendmail,pretix.plugins.statistics
    cookie_domain=.pretix.de

``instance_name``
    The name of this installation. Default: ``pretix.de``

``url``
    The installation's full URL, without a trailing slash.

``currency``
    The default currency as a three-letter code. Defaults to ``EUR``.

``datadir``
    The local path to a data directory that will be used for storing user uploads and similar
    data. Defaults to the value of the environment variable ``DATA_DIR`` or ``data``.

``plugins_default``
    A comma-separated list of plugins that are enabled by default for all new events.
    Defaults to ``pretix.plugins.sendmail,pretix.plugins.statistics``.

``cookie_domain``
    The cookie domain to be set. Defaults to ``None``.

``registration``
    Enables or disables the registration of new admin users. Defaults to ``on``.

``password_reset``
    Enables or disables password reset. Defaults to ``on``.

``long_sessions``
    Enables or disables the "keep me logged in" button. Defaults to ``on``.

``ecb_rates``
    By default, pretix periodically downloads a XML file from the European Central Bank to retrieve exchange rates
    that are used to print tax amounts in the customer currency on invoices for some currencies. Set to ``off`` to
    disable this feature. Defaults to ``on``.


Locale settings
---------------

Example::

    [locale]
    default=de
    timezone=Europe/Berlin

``default``
    The system's default locale. Default: ``en``

``timezone``
    The system's default timezone as a ``pytz`` name. Default: ``UTC``

Database settings
-----------------

Example::

    [database]
    backend=mysql
    name=pretix
    user=pretix
    password=abcd
    host=localhost
    port=3306

``backend``
    One of ``mysql``, ``sqlite3``, ``oracle`` and ``postgresql``.
    Default: ``sqlite3``.

    If you use MySQL, be sure to create your database using
    ``CREATE DATABASE <dbname> CHARACTER SET utf8;``. Otherwise, Unicode
    support will not properly work.

``name``
    The database's name. Default: ``db.sqlite3``.

``user``, ``password``, ``host``, ``port``
    Connection details for the database connection. Empty by default.

``galera``
    Indicates if the database backend is a MySQL/MariaDB Galera cluster and
    turns on some optimizations/special case handlers. Default: ``False``

URLs
----

Example::

    [urls]
    media=/media/
    static=/media/

``media``
    The URL to be used to serve user-uploaded content. You should not need to modify
    this. Default: ``/media/``

``static``
    The URL to be used to serve static files. You should not need to modify
    this. Default: ``/static/``

.. _`mail-settings`:

Email
-----

Example::

    [mail]
    from=hello@localhost
    host=127.0.0.71
    user=pretix
    password=foobar
    port=1025
    tls=on
    ssl=off

``host``, ``port``
    The SMTP Host to connect to. Defaults to ``localhost`` and ``25``.

``user``, ``password``
    The SMTP user data to use for the connection. Empty by default.

``from``
    The email address to set as ``From`` header in outgoing emails by the system.
    Default: ``pretix@localhost``

``tls``, ``ssl``
    Use STARTTLS or SSL for the SMTP connection. Off by default.

``admins``
    Comma-separated list of email addresses that should receive a report about every error code 500 thrown by pretix.

.. _`django-settings`:

Django settings
---------------

Example::

    [django]
    secret=j1kjps5a5&4ilpn912s7a1!e2h!duz^i3&idu@_907s$wrz@x-
    debug=off

``secret``
    The secret to be used by Django for signing and verification purposes. If this
    setting is not provided, pretix will generate a random secret on the first start
    and will store it in the filesystem for later usage.

``debug``
    Whether or not to run in debug mode. Default is ``False``.

    .. WARNING:: Never set this to ``True`` in production!

``profile``
    Enable code profiling for a random subset of requests. Disabled by default, see
    :ref:`perf-monitoring` for details.

.. _`metrics-settings`:

Metrics
-------

If you want to fetch internally collected prometheus-style metrics you need to configure the credentials for the
metrics endpoint and enable it::

    [metrics]
    enabled=true
    user=your_user
    passphrase=mysupersecretpassphrase

Currently, metrics-collection requires a redis server to be available.


Memcached
---------

You can use an existing memcached server as pretix's caching backend::

    [memcached]
    location=127.0.0.1:11211

``location``
    The location of memcached, either a host:port combination or a socket file.

If no memcached is configured, pretix will use Django's built-in local-memory caching method.

.. note:: If you use memcached and you deploy pretix across multiple servers, you should use *one*
          shared memcached instance, not multiple ones, because cache invalidations would not be
          propagated otherwise.

Redis
-----

If a redis server is configured, pretix can use it for locking, caching and session storage
to speed up various operations::

    [redis]
    location=redis://127.0.0.1:6379/1
    sessions=false

``location``
    The location of redis, as a URL of the form ``redis://[:password]@localhost:6379/0``
    or ``unix://[:password]@/path/to/socket.sock?db=0``

``session``
    When this is set to ``True``, redis will be used as the session storage.

If redis is not configured, pretix will store sessions and locks in the database. If memcached
is configured, memcached will be used for caching instead of redis.

Celery task queue
-----------------

For processing long-running tasks asynchronously, pretix requires the celery task queue.
For communication between the web server and the task workers in both direction, a messaging
queue and a result backend is needed. You can use a redis database for both directions, or
an AMQP server (e.g. RabbitMQ) as a broker and redis or your database as a result backend::

    [celery]
    broker=amqp://guest:guest@localhost:5672//
    backend=redis://localhost/0

RabbitMQ might be the better choice if you have a complex, multi-server, high-performance setup,
but as you already should have a redis instance ready for session and lock storage, we recommend
redis for convenience. See the `Celery documentation`_ for more details.

Sentry
------

pretix has native support for sentry, a tool that you can use to track errors in the
application. If you want to use sentry, you need to set a DSN in the configuration file::

    [sentry]
    dsn=https://<key>:<secret>@sentry.io/<project>

``dsn``
    You will be given this value by your sentry installation.


Secret length
-------------

If you are really paranoid, you can increase the length of random strings pretix uses in
various places like order codes, secrets in the ticket QR codes, etc. Example::

    [entropy]
    ; Order code needs to be < 16 characters, default is 5
    order_code=5
    ; Ticket secret needs to be < 64 characters, default is 32
    ticket_secret=32
    ; Voucher code needs to be < 255 characters, default is 16
    voucher_code=16

.. _Python documentation: https://docs.python.org/3/library/configparser.html?highlight=configparser#supported-ini-file-structure
.. _Celery documentation: http://docs.celeryproject.org/en/latest/configuration.html
