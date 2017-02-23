.. _`devsetup`:

The development setup
=====================

Obtain a copy of the source code
--------------------------------
You can just clone our git repository::

    git clone https://github.com/pretix/pretix.git
    cd pretix/

External Dependencies
---------------------
* Python 3.4 or newer
* ``pip`` for Python 3 (Debian package: ``python3-pip``)
* ``pyvenv`` for Python 3 (Debian package: ``python3-venv``)
* ``libffi`` (Debian package: ``libffi-dev``)
* ``libssl`` (Debian package: ``libssl-dev``)
* ``libxml2`` (Debian package ``libxml2-dev``)
* ``libxslt`` (Debian package ``libxslt1-dev``)
* ``msgfmt`` (Debian package ``gettext``)
* ``git``

Your local python environment
-----------------------------

Please execute ``python -V`` or ``python3 -V`` to make sure you have Python 3.4
(or newer) installed. Also make sure you have pip for Python 3 installed, you can
execute ``pip3 -V`` to check. Then use Python's internal tools to create a virtual
environment and activate it for your current session::

    pyvenv env
    source env/bin/activate

You should now see a ``(env)`` prepended to your shell prompt. You have to do this
in every shell you use to work with pretix (or configure your shell to do so
automatically). If you are working on Ubuntu or Debian, we strongly recommend upgrading
your pip and setuptools installation inside the virtual environment, otherwise some of
the dependencies might fail::

    pip3 install -U pip setuptools==28.6.1

Working with the code
---------------------
The first thing you need are all the main application's dependencies::

    cd src/
    pip3 install -r requirements.txt -r requirements/dev.txt

If you are working with Python 3.4, you will also need (you can skip this for Python 3.5)::

    pip3 install -r requirements/py34.txt

Next, you need to copy the SCSS files from the source folder to the STATIC_ROOT directory::

    python manage.py collectstatic --noinput

Then, create the local database::

    python manage.py migrate

A first user with username ``admin@localhost`` and password ``admin`` will be automatically
created. If you want to generate more test data, run::

    python make_testdata.py

If you want to see pretix in a different language than English, you have to compile our language
files::

    make localecompile

Run the development server
^^^^^^^^^^^^^^^^^^^^^^^^^^
To run the local development webserver, execute::

    python manage.py runserver

and head to http://localhost:8000/

As we did not implement an overall front page yet, you need to go directly to
http://localhost:8000/control/ for the admin view or, if you imported the test
data as suggested above, to the event page at http://localhost:8000/bigevents/2017/

.. _`checksandtests`:

Code checks and unit tests
^^^^^^^^^^^^^^^^^^^^^^^^^^
Before you check in your code into git, always run the static checkers and unit tests::

    flake8 .
    isort -c -rc .
    python manage.py check
    py.test

.. note:: If you have multiple CPU cores and want to speed up the test suite, you can install the python
          package ``pytest-xdist`` using ``pip3 install pytest-xdist`` and then run ``py.test -n NUM`` with
          ``NUM`` being the number of threads you want to use.

It is a good idea to put this command into your git hook ``.git/hooks/pre-commit``,
for example::

    #!/bin/sh
    cd $GIT_DIR/../src
    source ../env/bin/activate
    flake8 --ignore=E123,E128,F403,F401,N802,W503 .


Working with mails
^^^^^^^^^^^^^^^^^^
If you want to test anything regarding emails in your development setup, we recommend
starting Python's debugging SMTP server in a separate shell and configuring pretix to use it.
Every email will then be printed to the debugging SMTP server's stdout.

Add this to your ``src/pretix.cfg``::

    [mail]
    port = 1025

Then execute ``python -m smtpd -n -c DebuggingServer localhost:1025``.

Working with translations
^^^^^^^^^^^^^^^^^^^^^^^^^
If you want to translate new strings that are not yet known to the translation system,
you can use the following command to scan the source code for strings to be translated
and update the ``*.po`` files accordingly::

    make localegen

To actually see pretix in your language, you have to compile the ``*.po`` files to their
optimized binary ``*.mo`` counterparts::

    make localecompile


Working with the documentation
------------------------------
First, you should install the requirements necessary for building the documentation.
Make sure you have your virtual python environment activated (see above). Then, install the
packages by executing::

    cd doc/
    pip3 install -r requirements.txt

To build the documentation, run the following command from the ``doc/`` directory::

    make html

You will now find the generated documentation in the ``doc/_build/html/`` subdirectory.
