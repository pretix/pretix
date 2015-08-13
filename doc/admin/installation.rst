.. highlight:: ini

Installation
============

Requirements
------------
To use pretix, the most minimal setup consists of:

* **pretix** and the python packages it depends on
* An **WSGI application server** (we recommend gunicorn)

You get those two bundled in the ``pretix/standalone`` docker image.

If you want to set them up manually, you can also get pretix from GitHub or wait for us to set up proper
``pip`` packages and set up a simple gunicorn instance pointing to the ``pretix.wsgi`` endpoint.

To run pretix, you will need at least Python 3.2, although we recommend **Python 3.4** as we will
remove support for 3.2 soon and some features (like PDF output) already do not work with 3.2.

You can get the direct dependencies by doing a ``pip install -r requirements.txt`` in the pretix source
directory. You'll also need ``nodejs`` and the ``less`` node package. We'll provide detailled documentation
on this as soon as pretix will be officially released.

If you have real users on your system you'll **really** want to use

* A database (MySQL or PostgreSQL)
* A reverse proxy web server (nginx or Apache)

Optionally, you can speed up pretix by adding

* A memcached instance
* A redis database

We will provide a step-by-step tutorial with the first stable release, but all configuration
already :ref:`is documented <config>`.