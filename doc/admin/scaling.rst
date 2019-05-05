.. _`scaling`:

Scaling guide
=============

Our :ref:`installation guide <installation>` only covers "small-scale" setups, by which we mostly mean
setups that run on a **single (virtual) machine** and do not encounter large traffic peaks.

We do not offer an installation guide for larger-scale setups of pretix, mostly because we believe that
there is no one-size-fits-all solution for this and the desired setup highly depends on your use case,
the platform you run pretix on, and your technical capabilities. We do not recommend trying set up pretix
in a multi-server environment if you do not already have experience with managing server clusters.

This document is intended to give you a general idea on what issues you will encounter when you scale up
and what you should think of.

.. tip::

   If you require more help on this, we're happy to help. Our pretix Enterprise support team has built
   and helped building, scaling and load-testing pretix installations at any scale and we're looking
   forward to work with you on fine-tuning your system. If you intend to sell **more than a thousand
   tickets in a very short amount of time**, we highly recommend reaching out and at least talking this
   through. Just get in touch at sales@pretix.eu!

Scaling reasons
---------------

There's mainly two reasons to scale up a pretix installation beyond a single server:

* **Availability:** Distributing pretix over multiple servers can allow you to survive failure of one or more single machines, leading to a higher uptime and reliability of your system.

* **Traffic and throughput:** Distributing pretix over multiple servers can allow you to process more web requests and ticket sales at the same time.

You are very unlikely to require scaling for other reasons, such as having too much data in your database.

Components
----------

A pretix installation usually consists of the following components which run performance-relevant processes:

* ``pretix-web`` is the Django-based web application that serves all user interaction.

* ``pretix-worker`` is a Celery-based application that processes tasks that should be run asynchronously outside of the web application process.

* A **SQL database** keeps all the important data and processes the actual transactions. We recommend using PostgreSQL, but MySQL/MariaDB works as well.

* A **web server** that terminates TLS and HTTP connections and forwards them to ``pretix-web``. In some cases, e.g. when serving static files, the web servers might return a response directly. We recommend using ``nginx``.

* A **redis** server responsible for the communication between ``pretix-web`` and ``pretix-worker``, as well as for caching.

* A directory of **media files** such as user-uploaded files or generated files (tickets, invoices, …) that are created and used by ``pretix-web``, ``pretix-worker`` and the web server.

In the following, we will discuss the scaling behavior of every component individually. In general, you can run all of the components
on the same server, but you can just as well distribute every component to its own server, or even use multiple servers for some single
components.

.. warning::

   When setting up your system, don't forget about security. In a multi-server environment,
   you need to take special care to ensure that no unauthorized access to your database
   is possible through the network and that it's not easy to wiretap your connections. We
   recommend a rigorous use of firewalls and encryption on all communications. You can
   ensure this either on an application level (such as using the TLS support in your
   database) or on a network level with a VPN solution.

Web server
""""""""""

Your web server is at the very front of your installation. It will need to absorb all of the traffic, and it should be able to
at least show a decent error message, even when everything else fails. Luckily, web servers are really fast these days, so this
can be achieved without too much work.

We recommend reading up on tuning your web server for high concurrency. For nginx, this means thinking about the number of worker
processes and the number of connections each worker process accepts. Double-check that TLS session caching works, because TLS
handshakes can get really expensive.

During a traffic peak, your web server will be able to make us of more CPU resources, while memory usage will stay comparatively low,
so if you invest in more hardware here, invest in more and faster CPU cores.

Make sure that pretix' static files (such as CSS and JavaScript assets) as well as user-uploaded media files (event logos, etc)
are served directly by your web server and your web server caches them in-memory (nginx does it by default) and sets useful
headers for client-side caching. As an additional performance improvement, you can turn of access logging for these types of files.
If you want, you can even farm out serving static files to a different web server entirely and :ref:`configure pretix to reference
them from a different URL <config-urls>`.

.. tip::

   If you expect *really high traffic* for your very popular event, you might want to do some rate limiting on this layer, or,
   if you want to ensure a fair and robust first-come-first-served experience and prefer letting users wait over showing them
   errors, consider a queuing solution. We're happy to provide you with such systems, just get in touch at sales@pretix.eu.

pretix-web
""""""""""

The ``pretix-web`` process does not carry any internal state can be easily started on as many machines as you like, and you can
use the load balancing features of your frontend web server to redirect to all of them.

You can adjust the number of processes in the ``gunicorn`` command line, and we recommend choosing roughly two times the number
of CPU cores available. Under load, the memory consumption of ``pretix-web`` will stay comparatively constant, while the CPU usage
will increase a lot. Therefore, if you can add more or faster CPU cores, you will be able to serve more users.

pretix-worker
"""""""""""""

The ``pretix-worker`` process performs all operations that are not directly executed in the request-response-cycle of ``pretix-web``.
Just like ``pretix-web`` you can easily start up as many instances as you want on different machines to share the work. As long as they
all talk to the same redis server, they will all receive tasks from ``pretix-web``, work on them and post their result back.
You can configure the number of threads that run tasks in parallel through the ``--concurrency`` command line option of ``celery``.

Just like ``pretix-web``, this process is mostly heavy on CPU, disk IO and network IO, although memory peaks can occur e.g. during the
generation of large PDF files, so we recommend having some reserves here.

``pretix-worker`` performs a variety of tasks which are of different importance.
Some of them are mission-critical and need to be run quickly even during high load (such as
creating a cart or an order), others are irrelevant and can easily run later (such as
distributing tickets on the waiting list). You can fine-tune the capacity you assign to each
of these tasks by running ``pretix-worker`` processes that only work on a specific **queue**.
For example, you could have three servers dedicated only to process order creations and one
server dedicated only to sending emails. This allows you to set priorities and also protects
you from e.g. a slow email server lowering your ticket throughput.

You can do so by specifying one or more queues on the ``celery`` command line of this process, such as ``celery -A pretix.celery_app worker -Q notifications,mail``. Currently,
the following queues exist:

* ``checkout`` -- This queue handles everything related to carts and orders and thereby everything required to process a sale. This includes adding and deleting items from carts as well as creating and canceling orders.

* ``mail`` -- This queue handles sending of outgoing emails.

* ``notifications`` -- This queue handles the processing of any outgoing notifications, such as email notifications to admin users (except for the actual sending) or API notifications to registered webhooks.

* ``background`` -- This queue handles tasks that are expected to take long or have no human waiting for their result immediately, such as refreshing caches, re-generating CSS files, assigning tickets on the waiting list or parsing bank data files.

* ``default`` -- This queue handles everything else with "medium" or unassigned priority, most prominently the generation of files for tickets, invoices, badges, admin exports, etc.

Media files
"""""""""""

Both ``pretix-web``, ``pretix-worker`` and in some cases your webserver need to work with
media files. Media files are all files generated *at runtime* by the software. This can
include files uploaded by the event organizers, such as the event logo, files uploaded by
ticket buyers (if you use such features) or files generated by the software, such as
ticket files, invoice PDFs, data exports or customized CSS files.

Those files are by default stored to the ``media/`` sub-folder of the data directory given
in the ``pretix.cfg`` configuration file. Inside that ``media/`` folder, you will find a
``pub/`` folder containing the subset of files that should be publicly accessible through
the web server. Everything else only needs to be accessible by ``pretix-web`` and
``pretix-worker`` themselves.

If you distribute ``pretix-web`` or ``pretix-worker`` across more than one machine, you
**must** make sure that they all have access to a shared storage to read and write these
files, otherwise you **will** run into errors with the user interface.

The easiest solution for this is probably to store them on a NFS server that you mount
on each of the other servers.

Since we use Django's file storage mechanism internally, you can in theory also use a object-storage solution like Amazon S3, Ceph, or Minio to store these files, although we currently do not expose this through pretix' configuration file and this would require you to ship your own variant of ``pretix/settings.py`` and reference it through the ``DJANGO_SETTINGS_MODULE`` environment variable.

At pretix.eu, we use a custom-built `object storage cluster`_.

SQL database
""""""""""""

One of the most critical parts of the whole setup is the SQL database -- and certainly the
hardest to scale. Tuning relational databases is an art form, and while there's lots of
material on it on the internet, there's not a single recipe that you can apply to every case.

As a general rule of thumb, the more resources you can give your databases, the better.
Most databases will happily use all CPU cores available, but only use memory up to an amount
you configure, so make sure to set this memory usage as high as you can afford. Having more
memory available allows your database to make more use of caching, which is usually good.

Scaling your database to multiple machines needs to be treated with great caution. It's a
good to have a replica of your database for availability reasons. In case your primary
database server fails, you can easily switch over to the replica and continue working.

However, using database replicas for performance gains is much more complicated. When using
replicated database systems, you are always trading in consistency or availability to get
additional performance and the consequences of this can be subtle and it is important
that you have a deep understanding of the semantics of your replication mechanism.

.. warning::

   Using an off-the-shelf database proxy solution that redirects read queries to your
   replicas and write queries to your primary database **will lead to very nasty bugs.**

   As an example, if you buy a ticket, pretix first needs to calculate how many tickets
   are left to sell. If this calculation is done on a database replica that lags behind
   even for fractions of a second, the decision to allow selling the ticket will be made
   on out-of-data data and you can end up with more tickets sold than configured. Similarly,
   you could imagine situations leading to double payments etc.

If you do have a replica, you *can* tell pretix about it :ref:`in your configuration <config-replica>`.
This way, pretix can offload complex read-only queries to the replica when it is safe to do so.
As of pretix 2.6, this is mainly used for search queries in the backend and therefore does not really accelerate sales throughput, but we plan on expanding this in the future.

Therefore, for now our clear recommendation is: Try to scale your database vertically and put
it on the most powerful machine you have available.

redis
"""""

While redis is a very important part that glues together some of the components, it isn't used
heavily and can usually handle a fairly large pretix installation easily on a single modern
CPU core.
Having some memory available is good in case of e.g. lots of tasks queuing up during a traffic peak, but we wouldn't expect ever needing more than a gigabyte of it.

Feel free to set up a redis cluster for availability – but you won't need it for performance in a long time.

The locking issue
-----------------

Currently, there is one big issue with scaling pretix. We take the reliability and correctness
of pretix' core features very seriously and one part of this is that we want to make absolutely
sure that pretix never sells the wrong number of tickets or tickets it otherwise shouldn't sell.

However, due to pretix flexibility and complexity, ensuring this in a high-concurrency environment is really hard.
We're not just counting down integers, since quota availability in pretix depends on a multitude of factors and requires a handful of complex database queries to calculate.
We can't rely on database-level locking alone to get this right.

Therefore, we currently use a very drastic option:
During relevant actions that typically occur with high concurrency, such as creating carts and completing orders, we create a system-wide lock for the event and all other such
actions need to wait. In essence, this means **for a given event we're only ever selling
one ticket at a time**.

Therefore, it is currently very unlikely that you will be able to exceed **300-400 tickets per minute per event**.

For events up to a few thousand tickets, this isn't a problem and it's not even desirable to be able to sell much faster: If all tickets are reserved in the first minute, the shop shows a big "sold out" and everyone else goes away. Fifteen to thirty minutes later, depending on your settings, the first shopping carts will expire because people didn't actually go through with the purchase and tickets will become available again. This leads to a much more frustrating shopping experience for those trying to get a ticket than if tickets are sold at a slower pace and the first reservations expire before the last reservations are made. Not selling tickets through quickly (e.g. through a queue system) can do a lot to smooth out this process.

That said, we still want to fix this of course and make it possible to achieve much higher
throughput rates. We have some plans on how to soften this limitation, but they require
lots of time and effort to be realized. If you want to use pretix for an event with
10,000+ tickets that will be sold out within minutes, get in touch, we will make it work ;)


.. _object storage cluster: https://behind.pretix.eu/2018/03/20/high-available-cdn/