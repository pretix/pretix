.. highlight:: ini

Configuration file
==================

Pretix reads its configuration from a configuration file. It tries to find this file
at the following locations. It will try to read the file from the specified paths in
the following order. The file that is found *last* will override the settings from
the files found before.

1. ``/etc/pretix/pretix.cfg``
2. ``~/.pretix.cfg``
3. ``pretix.cfg`` in the current working directory

The file is expected to be in the INI format as specified in the `Python documentation`_.

The config file may contain the following sections (all settings are optional and have default values).

pretix settings
---------------

Example::

    [pretix]
    instance_name=pretix.de
    global_registration=off
    site_url=http://localhost
    currency=EUR
    cookiedomain=.pretix.de
    securecookie=on
    datadir=/data

``instance_name``
    The name of this installation. Default: ``pretix.de``

``global_registration``
    Whether or not this installation supports global user accounts (in addition to
    event-bound accounts). Defaults to ``True``.

``site_url``
    The installation's full URL, without a trailing slash.

``currency``
    The default currency as a three-letter code. Defaults to ``EUR``.

``cookiedomain``
    The domain to be used for session cookies, csrf protection cookies and locale cookies.
    Empty by default.

``securecookie``
    Set the ``secure`` and ``httponly`` flags on session cookies. Off by default.

``datadir``
    The local path to a data directory that will be used for storing user uploads and similar
    data.

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
    One of ``mysql``, ``sqlite3``, ``oracle`` and ``postgresql_psycopg2``.
    Default: ``sqlite3``.

``name``
    The database's name. Default: ``db.sqlite3``.

``user``, ``password``, ``host``, ``port``
    Connection details for the database connection. Empty by default.

URLs
-----

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

Django settings
---------------

Example::

    [django]
    hosts=localhost
    secret=j1kjps5a5&4ilpn912s7a1!e2h!duz^i3&idu@_907s$wrz@x-
    debug=off

``hosts``
    Comma-seperated list of allowed host names for this installation.
    Default: ``localhost``

``secret``
    The secret to be used by Django for signing and verification purposes. If this
    setting is not provided, pretix will generate a random secret on the first start
    and store it in the filesystem for later usage.

``debug``
    Whether or not to run in debug mode. Default is ``False``.

    .. WARNING:: Never set this to ``True`` in production!


.. _Python documentation: https://docs.python.org/3/library/configparser.html?highlight=configparser#supported-ini-file-structure