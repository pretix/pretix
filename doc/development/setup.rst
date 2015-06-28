The development setup
=====================

Obtain a copy of the source code
--------------------------------
Just clone our git repository including its submodules::

    git clone --recursive https://github.com/pretix/pretix.git 
    cd pretix/

External Dependencies
---------------------
* Python 3.4 or newer
* ``pip`` for Python 3
* ``git``
* ``lessc`` (Debian package: ``node-less``)

Your local python environment
-----------------------------

Please execute ``python -V`` or ``python3 -V`` to make sure you have Python 3.4 
installed. Also make sure you have pip for Python 3 installed, you can execute 
``pip3 -V`` to check. Then use Python 3.4's internal tools to create a virtual 
environment and activate it for your current session::

    pyvenv env
    source env/bin/activate

You should now see a ``(env)`` prepended to your shell prompt. You have to do this
in every shell you use to work with pretix (or configure your shell to do so 
automatically).

Working with the code
---------------------
The first thing you need are all the main application's dependencies::

    cd src/
    pip install -r requirements.txt

Then, create the local database::

    python manage.py migrate

A first user with username ``admin@localhost`` and password ``admin`` will be automatically
created. If you want to genreate more test data, run::

    python make_testdata.py

Create the translation files
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
If you're working with the translation, you can use the following command to scan the
source code for strings to be translated and update the ``*.po`` files accordingly::

    make localegen

To actually see pretix in your language, you have to compile the ``*.po`` files to their
optimized binary ``*.mo`` counterparts::

    make localecompile

Run the development server
^^^^^^^^^^^^^^^^^^^^^^^^^^
To run the local development webserver, execute::

    python manage.py runserver

and head to http://localhost:8000/

Code checks and unit tests
^^^^^^^^^^^^^^^^^^^^^^^^^^
Before you check in your code into git, always run the static checkers and unit tests::

    flake8 .
    python manage.py validate
    py.test

The ``flake8`` command by default is a bit stricter than what we really enforce, but we do enforce that all commits
produce no output from::

    flake8 --ignore=E123,E128,F403,F401,N802,W503 .

It is therefore a good idea to put this command into your git hook ``.git/hooks/pre-commit``,
for example::

    #!/bin/sh
    cd $GIT_DIR/../src
    source ../env/bin/activate
    flake8 --ignore=E123,E128,F403,F401,N802,W503 .



Working with the documentation
------------------------------
First, you should install the requirements necessary for building the documentation. 
Make sure you have your virtual python enviroment activated (see above). Then, install the 
packages by executing::

    cd doc/
    pip install -r requirements.txt

To build the documentation, run the following command from the ``doc/`` directory::

    make html

You will now find the generated documentation in the ``doc/_build/html/`` subdirectory.
