.. _`devsetup`:

Development setup
=================

This tutorial helps you to get started hacking with pretix on your own computer. You need this to
be able to contribute to pretix, but it might also be helpful if you want to write your own plugins.
If you want to install pretix on a server for actual usage, go to the `administrator documentation`_ instead.

Obtain a copy of the source code
--------------------------------
You can just clone our git repository::

    git clone https://github.com/pretix/pretix.git
    cd pretix/

External Dependencies
---------------------
Your should install the following on your system:

* Python 3.9 or newer
* ``pip`` for Python 3 (Debian package: ``python3-pip``)
* ``python-dev`` for Python 3 (Debian package: ``python3-dev``)
* On Debian/Ubuntu: ``python-venv`` for Python 3 (Debian package: ``python3-venv``)
* ``libffi`` (Debian package: ``libffi-dev``)
* ``libssl`` (Debian package: ``libssl-dev``)
* ``libxml2`` (Debian package ``libxml2-dev``)
* ``libxslt`` (Debian package ``libxslt1-dev``)
* ``libenchant-2-2`` (Debian package ``libenchant-2-2``)
* ``msgfmt`` (Debian package ``gettext``)
* ``git``

Your local python environment
-----------------------------

Please execute ``python -V`` or ``python3 -V`` to make sure you have Python 3.9
(or newer) installed. Also make sure you have pip for Python 3 installed, you can
execute ``pip3 -V`` to check. Then use Python's internal tools to create a virtual
environment and activate it for your current session::

    python3 -m venv env
    source env/bin/activate

You should now see a ``(env)`` prepended to your shell prompt. You have to do this
in every shell you use to work with pretix (or configure your shell to do so
automatically). If you are working on Ubuntu or Debian, we strongly recommend upgrading
your pip and setuptools installation inside the virtual environment, otherwise some of
the dependencies might fail::

    pip3 install -U pip setuptools

Working with the code
---------------------
If you do not have a recent installation of ``nodejs``, install it now::

    curl -sL https://deb.nodesource.com/setup_17.x | sudo -E bash -
    sudo apt install nodejs

To make sure it is on your path variable, close and reopen your terminal. Now, install the Python-level dependencies of pretix::

    pip3 install -e ".[dev]"

Next, you need to copy the SCSS files from the source folder to the STATIC_ROOT directory::

    cd src/
    python manage.py collectstatic --noinput

Then, create the local database::

    python manage.py migrate

A first user with username ``admin@localhost`` and password ``admin`` will be automatically
created.

You will also need to install a few JavaScript dependencies::

    make npminstall

If you want to see pretix in a different language than English, you have to compile our language
files::

    make localecompile

Run the development server
^^^^^^^^^^^^^^^^^^^^^^^^^^
To run the local development webserver, execute::

    python manage.py runserver

and head to http://localhost:8000/

As we did not implement an overall front page yet, you need to go directly to
http://localhost:8000/control/ for the admin view.

.. note:: If you want the development server to listen on a different interface or
          port (for example because you develop on `pretixdroid`_), you can check
          `Django's documentation`_ for more options.

When running the local development webserver, ensure Celery is not configured
in ``pretix.cfg``. i.e., you should remove anything such as::

    [celery]
    backend=redis://redis:6379/2
    broker=redis://redis:6379/2

If you choose to use Celery for development, you must also start a Celery worker
process::

    celery -A pretix.celery_app worker -l info

However, beware that code changes will not auto-reload within Celery.

.. _`checksandtests`:

Code checks and unit tests
^^^^^^^^^^^^^^^^^^^^^^^^^^
Before you check in your code into git, always run static checkers and linters. If any of these commands fail,
your pull request will not be merged into pretix. If you have trouble figuring out *why* they fail, create your
pull request nevertheless and ask us for help, we are happy to assist you.

Execute the following commands to check for code style errors::

    flake8 .
    isort -c .
    python manage.py check

Execute the following command to run pretix' test suite (might take a couple of minutes)::

    py.test

.. note:: If you have multiple CPU cores and want to speed up the test suite, you can install the python
          package ``pytest-xdist`` using ``pip3 install pytest-xdist`` and then run ``py.test -n NUM`` with
          ``NUM`` being the number of threads you want to use.

It is a good idea to put this command into your git hook ``.git/hooks/pre-commit``,
for example, to check for any errors in any staged files when committing::

    #!/bin/bash

    source ../env/bin/activate  # Adjust to however you activate your virtual environment
    for file in $(git diff --cached --name-only | grep -E '\.py$' | grep -Ev "migrations|mt940\.py|pretix/settings\.py|make_testdata\.py|testutils/settings\.py|tests/settings\.py|pretix/base/models/__init__\.py|.*_pb2\.py")
    do
      echo $file
      git show ":$file" | flake8 - --stdin-display-name="$file" || exit 1 # we only want to lint the staged changes, not any un-staged changes
      git show ":$file" | isort -c - | grep ERROR && exit 1 || true
    done



This keeps you from accidentally creating commits violating the style guide.

Working with mails
^^^^^^^^^^^^^^^^^^
If you want to test anything regarding emails in your development setup, we recommend
starting Python's debugging SMTP server in a separate shell and configuring pretix to use it.
Every email will then be printed to the debugging SMTP server's stdout.

Add this to your ``src/pretix.cfg``::

    [mail]
    port = 1025

Then execute ``python -m smtpd -n -c DebuggingServer localhost:1025``.

Working with periodic tasks
^^^^^^^^^^^^^^^^^^^^^^^^^^^
Periodic tasks (like sendmail rules) are run when an external scheduler (like cron)
triggers the ``runperiodic`` command.

To run periodic tasks, execute ``python manage.py runperiodic``.

Working with translations
^^^^^^^^^^^^^^^^^^^^^^^^^
If you want to translate new strings that are not yet known to the translation system,
you can use the following command to scan the source code for strings to be translated
and update the ``*.po`` files accordingly::

    make localegen

However, most of the time you don't need to care about this. Just create your pull request
with functionality and English strings only, and we'll push the new translation strings
to our translation platform after the merge.

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

You will now find the generated documentation in the ``doc/_build/html/`` subdirectory. If you work
with the documentation a lot, you might find it useful to use sphinx-autobuild::

    pip3 install sphinx-autobuild
    sphinx-autobuild . _build/html -p 8081

Then, go to http://localhost:8081 for a version of the documentation that automatically re-builds
whenever you change a source file.

Working with frontend assets
----------------------------

To update the frontend styles of shops with a custom styling, run the following commands inside
your virtual environment.::

    python -m pretix collectstatic --noinput
    python -m pretix updateassets


.. _Django's documentation: https://docs.djangoproject.com/en/1.11/ref/django-admin/#runserver
.. _pretixdroid: https://github.com/pretix/pretixdroid
.. _administrator documentation: https://docs.pretix.eu/self-hosting/
