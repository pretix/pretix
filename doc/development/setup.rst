The development setup
=====================

Obtain a copy of the source code
--------------------------------
Just clone our git repository::

    git clone https://github.com/tixl/tixl.git
    cd tixl/

Your local python environment
-----------------------------

Please execute ``python -V`` or ``python3 -V`` to make sure you have Python 3.4 installed. Also make sure you have pip for Python 3 installed, you can execute ``pip3 -V`` to check. Then use Python 3.4's internal tools to create a virtual environment and activate it for your current session::

    pyvenv env
    source env/bin/activate

You should now see a ``(env)`` prepended to your shell prompt.

Working with the documentation
------------------------------
First, you should install the requiremente necessary for building the documentation. Make sure you have your virtual python enviroment activated (see above). Then, install the packages by executing::

    cd doc/
    pip install -r requirements.txt

To build the documentation, run the following command from the ``doc/`` directory::

    make html

You will now find the generated documentation in the ``doc/_build/html/`` subdirectory.
