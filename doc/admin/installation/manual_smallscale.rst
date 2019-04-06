.. highlight:: none

Small-scale manual deployment
=============================

This guide describes the installation of a small-scale installation of pretix from source. By small-scale, we mean
that everything is being run on one host and you don't expect thousands of participants trying to get a ticket within
a few minutes. In this setup, you will have to perform a number of manual steps. If you prefer using a container
solution with many things readily set-up, look at :ref:`dockersmallscale`.

.. warning:: Even though we try to make it straightforward to run pretix, it still requires some Linux experience to
             get it right. If you're not feeling comfortable managing a Linux server, check out our hosting and service
             offers at `pretix.eu`_.

We tested this guide on the Linux distribution **Debian 8.0** but it should work very similar on other
modern distributions, especially on all systemd-based ones.

Requirements
------------

Please set up the following systems beforehand, we'll not explain them here in detail (but see these links for external
installation guides):

* A SMTP server to send out mails, e.g. `Postfix`_ on your machine or some third-party server you have credentials for
* A HTTP reverse proxy, e.g. `nginx`_ or Apache to allow HTTPS connections
* A `PostgreSQL`_, `MySQL`_ 5.7+, or MariaDB 10.2.7+ database server
* A `redis`_ server

We also recommend that you use a firewall, although this is not a pretix-specific recommendation. If you're new to
Linux and firewalls, we recommend that you start with `ufw`_.

.. note:: Please, do not run pretix without HTTPS encryption. You'll handle user data and thanks to `Let's Encrypt`_
          SSL certificates can be obtained for free these days. We also *do not* provide support for HTTP-only
          installations except for evaluation purposes.

.. warning:: We recommend **PostgreSQL**. If you go for MySQL, make sure you run **MySQL 5.7 or newer** or
             **MariaDB 10.2.7 or newer**.

Unix user
---------

As we do not want to run pretix as root, we first create a new unprivileged user::

    # adduser pretix --disabled-password --home /var/pretix

In this guide, all code lines prepended with a ``#`` symbol are commands that you need to execute on your server as
``root`` user (e.g. using ``sudo``); all lines prepended with a ``$`` symbol should be run by the unprivileged user.

Database
--------

Having the database server installed, we still need a database and a database user. We can create these with any kind
of database managing tool or directly on our database's shell. For PostgreSQL, we would do::

    # sudo -u postgres createuser pretix
    # sudo -u postgres createdb -O pretix pretix

When using MySQL, make sure you set the character set of the database to ``utf8mb4``, e.g. like this::

    mysql > CREATE DATABASE pretix DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_unicode_ci;

Package dependencies
--------------------

To build and run pretix, you will need the following debian packages::

    # apt-get install git build-essential python-dev python3-venv python3 python3-pip \
                      python3-dev libxml2-dev libxslt1-dev libffi-dev zlib1g-dev libssl-dev \
                      gettext libpq-dev libmariadbclient-dev libjpeg-dev libopenjp2-7-dev

Config file
-----------

We now create a config directory and config file for pretix::

    # mkdir /etc/pretix
    # touch /etc/pretix/pretix.cfg
    # chown -R pretix:pretix /etc/pretix/
    # chmod 0600 /etc/pretix/pretix.cfg

Fill the configuration file ``/etc/pretix/pretix.cfg`` with the following content (adjusted to your environment)::

    [pretix]
    instance_name=My pretix installation
    url=https://pretix.mydomain.com
    currency=EUR
    datadir=/var/pretix/data

    [database]
    ; For MySQL, replace with "mysql"
    backend=postgresql
    name=pretix
    user=pretix
    ; For MySQL, enter the user password. For PostgreSQL on the same host,
    ; we don't need one because we can use peer authentification if our
    ; PostgreSQL user matches our unix user.
    password=
    ; For MySQL, use local socket, e.g. /var/run/mysqld/mysqld.sock
    ; For a remote host, supply an IP address
    ; For local postgres authentication, you can leave it empty
    host=

    [mail]
    ; See config file documentation for more options
    from=tickets@yourdomain.com
    host=127.0.0.1

    [redis]
    location=redis://127.0.0.1/0
    sessions=true

    [celery]
    backend=redis://127.0.0.1/1
    broker=redis://127.0.0.1/2

See :ref:`email configuration <mail-settings>` to learn more about configuring mail features.

Install pretix from PyPI
------------------------

Now we will install pretix itself. The following steps are to be executed as the ``pretix`` user. Before we
actually install pretix, we will create a virtual environment to isolate the python packages from your global
python installation::

    $ python3 -m venv /var/pretix/venv
    $ source /var/pretix/venv/bin/activate
    (venv)$ pip3 install -U pip setuptools wheel

We now install pretix, its direct dependencies and gunicorn. Replace ``postgres`` with ``mysql`` in the following
command if you're running MySQL::

    (venv)$ pip3 install "pretix[postgres]" gunicorn

Note that you need Python 3.5 or newer. You can find out your Python version using ``python -V``.

We also need to create a data directory::

    (venv)$ mkdir -p /var/pretix/data/media

Finally, we compile static files and translation data and create the database structure::

    (venv)$ python -m pretix migrate
    (venv)$ python -m pretix rebuild


Start pretix as a service
-------------------------

We recommend starting pretix using systemd to make sure it runs correctly after a reboot. Create a file
named ``/etc/systemd/system/pretix-web.service`` with the following content::

    [Unit]
    Description=pretix web service
    After=network.target

    [Service]
    User=pretix
    Group=pretix
    Environment="VIRTUAL_ENV=/var/pretix/venv"
    Environment="PATH=/var/pretix/venv/bin:/usr/local/bin:/usr/bin:/bin"
    ExecStart=/var/pretix/venv/bin/gunicorn pretix.wsgi \
                          --name pretix --workers 5 \
                          --max-requests 1200  --max-requests-jitter 50 \
                          --log-level=info --bind=127.0.0.1:8345
    WorkingDirectory=/var/pretix
    Restart=on-failure

    [Install]
    WantedBy=multi-user.target

For background tasks we need a second service ``/etc/systemd/system/pretix-worker.service`` with the following content::

    [Unit]
    Description=pretix background worker
    After=network.target

    [Service]
    User=pretix
    Group=pretix
    Environment="VIRTUAL_ENV=/var/pretix/venv"
    Environment="PATH=/var/pretix/venv/bin:/usr/local/bin:/usr/bin:/bin"
    ExecStart=/var/pretix/venv/bin/celery -A pretix.celery_app worker -l info
    WorkingDirectory=/var/pretix
    Restart=on-failure

    [Install]
    WantedBy=multi-user.target

You can now run the following commands to enable and start the services::

    # systemctl daemon-reload
    # systemctl enable pretix-web pretix-worker
    # systemctl start pretix-web pretix-worker


Cronjob
-------

You need to set up a cronjob that runs the management command ``runperiodic``. The exact interval is not important
but should be something between every minute and every hour. You could for example configure cron like this::

    15,45 * * * * export PATH=/var/pretix/venv/bin:$PATH && cd /var/pretix && python -m pretix runperiodic

The cronjob should run as the ``pretix`` user (``crontab -e -u pretix``).

SSL
---

The following snippet is an example on how to configure a nginx proxy for pretix::

    server {
        listen 80 default_server;
        listen [::]:80 ipv6only=on default_server;
        server_name pretix.mydomain.com;
    }
    server {
        listen 443 default_server;
        listen [::]:443 ipv6only=on default_server;
        server_name pretix.mydomain.com;

        ssl on;
        ssl_certificate /path/to/cert.chain.pem;
        ssl_certificate_key /path/to/key.pem;

        add_header Referrer-Policy same-origin;
        add_header X-Content-Type-Options nosniff;

        location / {
            proxy_pass http://localhost:8345/;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
            proxy_set_header Host $http_host;
        }

        location /media/ {
            alias /var/pretix/data/media/;
            expires 7d;
            access_log off;
        }

        location ^~ /media/cachedfiles {
            deny all;
            return 404;
        }
        location ^~ /media/invoices {
            deny all;
            return 404;
        }

        location /static/ {
            alias /var/pretix/venv/lib/python3.5/site-packages/pretix/static.dist/;
            access_log off;
            expires 365d;
            add_header Cache-Control "public";
        }
    }

.. note:: Remember to replace the ``python3.5`` in the ``/static/`` path in the config 
          above with your python version.

We recommend reading about setting `strong encryption settings`_ for your web server.

Next steps
----------

Yay, you are done! You should now be able to reach pretix at https://pretix.yourdomain.com/control/ and log in as
*admin@localhost* with a password of *admin*. Don't forget to change that password! Create an organizer first, then
create an event and start selling tickets!

You should probably read :ref:`maintainance` next.

Updates
-------

.. warning:: While we try hard not to break things, **please perform a backup before every upgrade**.

To upgrade to a new pretix release, pull the latest code changes and run the following commands (again, replace
``postgres`` with ``mysql`` if necessary)::

    $ source /var/pretix/venv/bin/activate
    (venv)$ pip3 install -U pretix[postgres] gunicorn
    (venv)$ python -m pretix migrate
    (venv)$ python -m pretix rebuild
    (venv)$ python -m pretix updatestyles
    # systemctl restart pretix-web pretix-worker


.. _`manual_plugininstall`:

Install a plugin
----------------

To install a plugin, just use ``pip``! Depending on the plugin, you should probably apply database migrations and
rebuild the static files afterwards. Replace ``pretix-passbook`` with the plugin of your choice in the following
example::

    $ source /var/pretix/venv/bin/activate
    (venv)$ pip3 install pretix-passbook
    (venv)$ python -m pretix migrate
    (venv)$ python -m pretix rebuild
    # systemctl restart pretix-web pretix-worker


.. _Postfix: https://www.digitalocean.com/community/tutorials/how-to-install-and-configure-postfix-as-a-send-only-smtp-server-on-ubuntu-16-04
.. _nginx: https://botleg.com/stories/https-with-lets-encrypt-and-nginx/
.. _Let's Encrypt: https://letsencrypt.org/
.. _pretix.eu: https://pretix.eu/
.. _MySQL: https://dev.mysql.com/doc/refman/5.7/en/linux-installation-apt-repo.html
.. _PostgreSQL: https://www.digitalocean.com/community/tutorials/how-to-install-and-use-postgresql-9-4-on-debian-8
.. _redis: https://blog.programster.org/debian-8-install-redis-server/
.. _ufw: https://en.wikipedia.org/wiki/Uncomplicated_Firewall
.. _strong encryption settings: https://mozilla.github.io/server-side-tls/ssl-config-generator/
