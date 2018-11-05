.. highlight:: none

.. _`dockersmallscale`:

Small-scale deployment with Docker
==================================

This guide describes the installation of a small-scale installation of pretix using docker. By small-scale, we mean
that everything is being run on one host and you don't expect thousands of participants trying to get a ticket within
a few minutes. In this setup, as many parts of pretix as possible are hidden away in one single docker container.
This has some trade-offs in terms of performance and isolation but allows a rather easy installation.

.. warning:: Even though we try to make it straightforward to run pretix, it still requires some Linux experience to
             get it right. If you're not feeling comfortable managing a Linux server, check out our hosting and service
             offers at `pretix.eu`_.

We tested this guide on the Linux distribution **Debian 8.0** but it should work very similar on other
modern distributions, especially on all systemd-based ones.

Requirements
------------

Please set up the following systems beforehand, we'll not explain them here (but see these links for external
installation guides):

* `Docker`_
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

On this guide
-------------

All code lines prepended with a ``#`` symbol are commands that you need to execute on your server as ``root`` user;
all lines prepended with a ``$`` symbol can also be run by an unprivileged user.

Data files
----------

First of all, you need to create a directory on your server that pretix can use to store data files and make that
directory writable to the user that runs pretix inside the docker container::

    # mkdir /var/pretix-data
    # chown -R 15371:15371 /var/pretix-data

Database
--------

Next, we need a database and a database user. We can create these with any kind of database managing tool or directly on
our database's shell, e.g. for MySQL::

    $ mysql -u root -p
    mysql> CREATE DATABASE pretix DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_unicode_ci;
    mysql> GRANT ALL PRIVILEGES ON pretix.* TO pretix@'localhost' IDENTIFIED BY '*********';
    mysql> FLUSH PRIVILEGES;

Replace the asterisks with a password of your own. For MySQL, we will use a unix domain socket to connect to the
database. For PostgreSQL, be sure to configure the interface binding and your firewall so that the docker container
can reach PostgreSQL.

Redis
-----

For caching and messaging in small-scale setups, pretix recommends using redis. In this small-scale setup we assume a
redis instance to be running on the same host. To avoid the hassle with network configurations and firewalls, we
recommend connecting to redis via a unix socket. To enable redis on unix sockets, add the following to your
``/etc/redis/redis.conf``::

    unixsocket /var/run/redis/redis.sock
    unixsocketperm 777

Now restart redis-server::

    # systemctl restart redis-server

.. warning:: Setting the socket permissions to 777 is a possible security problem. If you have untrusted users on your
             system or have high security requirements, please don't do this and let redis listen to a TCP socket
             instead. We recommend the socket approach because the TCP socket in combination with docker's networking
             can easily become an even worse security hole when configured slightly wrong. Read more about security
             on the `redis website`_.

             Another possible solution is to run `redis in docker`_ and link the containers using docker's networking
             features.

Config file
-----------

We now create a config directory and config file for pretix::

    # mkdir /etc/pretix
    # touch /etc/pretix/pretix.cfg
    # chown -R 15371:15371 /etc/pretix/
    # chmod 0700 /etc/pretix/pretix.cfg

Fill the configuration file ``/etc/pretix/pretix.cfg`` with the following content (adjusted to your environment)::

    [pretix]
    instance_name=My pretix installation
    url=https://pretix.mydomain.com
    currency=EUR
    ; DO NOT change the following value, it has to be set to the location of the
    ; directory *inside* the docker container
    datadir=/data

    [database]
    ; Replace mysql with postgresql_psycopg2 for PostgreSQL
    backend=mysql
    name=pretix
    user=pretix
    password=*********
    ; Replace with host IP address for PostgreSQL
    host=/var/run/mysqld/mysqld.sock

    [mail]
    ; See config file documentation for more options
    from=tickets@yourdomain.com
    ; This is the default IP address of your docker host in docker's virtual
    ; network. Make sure postfix listens on this address.
    host=172.17.0.1

    [redis]
    location=unix:///var/run/redis/redis.sock?db=0
    ; Remove the following line if you are unsure about your redis' security
    ; to reduce impact if redis gets compromised.
    sessions=true

    [celery]
    backend=redis+socket:///var/run/redis/redis.sock?virtual_host=1
    broker=redis+socket:///var/run/redis/redis.sock?virtual_host=2

See :ref:`email configuration <mail-settings>` to learn more about configuring mail features.

Docker image and service
------------------------

First of all, download the latest stable pretix image by running::

    $ docker pull pretix/standalone:stable

We recommend starting the docker container using systemd to make sure it runs correctly after a reboot. Create a file
named ``/etc/systemd/system/pretix.service`` with the following content::

    [Unit]
    Description=pretix
    After=docker.service
    Requires=docker.service

    [Service]
    TimeoutStartSec=0
    ExecStartPre=-/usr/bin/docker kill %n
    ExecStartPre=-/usr/bin/docker rm %n
    ExecStart=/usr/bin/docker run --name %n -p 8345:80 \
        -v /var/pretix-data:/data \
        -v /etc/pretix:/etc/pretix \
        -v /var/run/redis:/var/run/redis \
        -v /var/run/mysqld:/var/run/mysqld \
        pretix/standalone:stable all
    ExecStop=/usr/bin/docker stop %n

    [Install]
    WantedBy=multi-user.target

You can leave the MySQL socket volume out if you're using PostgreSQL. You can now run the following commands
to enable and start the service::

    # systemctl daemon-reload
    # systemctl enable pretix
    # systemctl start pretix

Cronjob
-------

You need to set up a cronjob that runs the management command ``runperiodic``. The exact interval is not important
but should be something between every minute and every hour. You could for example configure cron like this::

    15,45 * * * * /usr/bin/docker exec pretix.service pretix cron

The cronjob may run as any user that can use the docker daemon.

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

        location / {
            proxy_pass http://localhost:8345/;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
            proxy_set_header Host $http_host;
        }
    }


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

Updates are fairly simple, but require at least a short downtime::

    # docker pull pretix/standalone:stable
    # systemctl restart pretix.service
    # docker exec -it pretix.service pretix upgrade

Restarting the service can take a few seconds, especially if the update requires changes to the database.
Replace ``stable`` above with a specific version number like ``1.0`` or with ``latest`` for the development
version, if you want to.

.. _`docker_plugininstall`:

Install a plugin
----------------

To install a plugin, you need to build your own docker image. To do so, create a new directory and place a file
named ``Dockerfile`` in it. The Dockerfile could look like this (replace ``pretix-passbook`` with the plugins of your
choice)::

    FROM pretix/standalone:stable
    USER root
    RUN pip3 install pretix-passbook
    USER pretixuser
    RUN cd /pretix/src && make production

Then, go to that directory and build the image::

    $ docker build -t mypretix

You can now use that image ``mypretix`` instead of ``pretix/standalone`` in your service file (see above). Be sure
to re-build your custom image after you pulled ``pretix/standalone`` if you want to perform an update.

.. _Docker: https://docs.docker.com/engine/installation/linux/debian/
.. _Postfix: https://www.digitalocean.com/community/tutorials/how-to-install-and-configure-postfix-as-a-send-only-smtp-server-on-ubuntu-16-04
.. _nginx: https://botleg.com/stories/https-with-lets-encrypt-and-nginx/
.. _Let's Encrypt: https://letsencrypt.org/
.. _pretix.eu: https://pretix.eu/
.. _MySQL: https://dev.mysql.com/doc/refman/5.7/en/linux-installation-apt-repo.html
.. _PostgreSQL: https://www.digitalocean.com/community/tutorials/how-to-install-and-use-postgresql-9-4-on-debian-8
.. _redis: https://blog.programster.org/debian-8-install-redis-server/
.. _ufw: https://en.wikipedia.org/wiki/Uncomplicated_Firewall
.. _redis website: https://redis.io/topics/security
.. _redis in docker: https://hub.docker.com/r/_/redis/
.. _strong encryption settings: https://mozilla.github.io/server-side-tls/ssl-config-generator/
