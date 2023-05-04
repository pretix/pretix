.. highlight:: none

Migrating from MySQL/MariaDB to PostgreSQL
==========================================

Our recommended database for all production installations is PostgreSQL. Support for MySQL/MariaDB will be removed in
pretix 5.0.

In order to follow this guide, your pretix installation needs to be a version that fully supports MySQL/MariaDB. If you
already upgraded to pretix 5.0, downgrade back to the last 4.x release using ``pip``.

.. note:: We have tested this guide carefully, but we can't assume any liability for its correctness. The data loss
          risk should be low as long as pretix is not running while you do the migration. If you are a pretix Enterprise
          customer, feel free to reach out in advance if you want us to support you along the way.

Update database schema
----------------------

Before you start, make sure your database schema is up to date::

    # sudo -u pretix -s
    $ source /var/pretix/venv/bin/activate
    (venv)$ python -m pretix migrate

Install PostgreSQL
------------------

Now, install and set up a PostgreSQL server. For a local installation on Debian or Ubuntu, use::

    # apt install postgresql

Having the database server installed, we still need a database and a database user. We can create these with any kind
of database managing tool or directly on our database's shell. Please make sure that UTF8 is used as encoding for the
best compatibility. You can check this with the following command::

    # sudo -u postgres psql -c 'SHOW SERVER_ENCODING'

Without Docker
""""""""""""""

For our standard manual installation, create the database and user like this::

    # sudo -u postgres createuser pretix
    # sudo -u postgres createdb -O pretix pretix

With Docker
"""""""""""

For our standard docker installation, create the database and user like this::

    # sudo -u postgres createuser -P pretix
    # sudo -u postgres createdb -O pretix pretix

Make sure that your database listens on the network. If PostgreSQL on the same same host as docker, but not inside a docker container, we recommend that you listen on the Docker interface by changing the following line in ``/etc/postgresql/<version>/main/postgresql.conf``::

    listen_addresses = 'localhost,172.17.0.1'

You also need to add a new line to ``/etc/postgresql/<version>/main/pg_hba.conf`` to allow network connections to this user and database::

    host    pretix          pretix          172.17.0.1/16           md5

Restart PostgreSQL after you changed these files::

    # systemctl restart postgresql

If you have a firewall running, you should also make sure that port 5432 is reachable from the ``172.17.0.1/16`` subnet.

Of course, instead of all this you can also run a PostgreSQL docker container and link it to the pretix container.

Stop pretix
-----------

To prevent any more changes to your data, stop pretix from running::

    # systemctl stop pretix-web pretix-worker

Change configuration
--------------------

Change the database configuration in your ``/etc/pretix/pretix.cfg`` file::

    [database]
    backend=postgresql
    name=pretix
    user=pretix
    password=  ; only required for docker or remote database, can be kept empty for local auth
    host=      ; set to 172.17.0.1 in docker setup, keep empty for local auth


Create database schema
-----------------------

To create the schema in your new PostgreSQL database, use the following commands::

    # sudo -u pretix -s
    $ source /var/pretix/venv/bin/activate
    (venv)$ python -m pretix migrate


Migrate your data
-----------------

Install ``pgloader``::

    # apt install pgloader

.. note::

   If you are using Ubuntu 20.04, the ``pgloader`` version from the repositories seems to be incompatible with PostgreSQL
   12+. You can install ``pgloader`` from the `PostgreSQL repositories`_ instead.
   See also `this discussion <https://github.com/pretix/pretix/issues/3090>`_.

Create a new file ``/tmp/pretix.load``, replacing the MySQL and PostgreSQL connection strings with the correct user names, passwords, and/or database names::

    LOAD DATABASE
        FROM mysql://pretix:password@localhost/pretix  -- replace with mysql://username:password@hostname/dbname
        INTO postgresql:///pretix                      -- replace with dbname

    WITH data only, include no drop, truncate, disable triggers,
         create no indexes, drop indexes, reset sequences

    ALTER SCHEMA 'pretix' RENAME TO 'public'           -- replace pretix with the name of the MySQL database

    ALTER TABLE NAMES MATCHING ~/.*/
        SET SCHEMA 'public'

    SET timezone TO '+00:00'

    SET PostgreSQL PARAMETERS
         maintenance_work_mem to '128MB',
         work_mem to '12MB';

Then, run::

    # sudo -u postgres pgloader /tmp/pretix.load

The output should end with a table summarizing the results for every table. You can ignore warnings about type casts
and missing constraints.

Afterwards, delete the file again::

    # rm -rf /tmp/pretix.load

Start pretix
------------

Now, restart pretix. Maybe stop your MySQL server as a verification step that you are no longer using it::

    # systemctl stop mariadb
    # systemctl start pretix-web pretix-worker

And you're done! After you've verified everything has been copied correctly, you can delete the old MySQL database.

.. note:: Don't forget to update your backup process to back up your PostgreSQL database instead of your MySQL database now.

Troubleshooting
---------------

Peer authentication failed
""""""""""""""""""""""""""

Sometimes you might see an error message like this::

    django.db.utils.OperationalError: connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed: FATAL:  Peer authentication failed for user "pretix"

It is important to understand that PostgreSQL by default offers two types of authentication:

- **Peer authentication**, which works automatically based on the Linux user you are working as. This requires that
  the connection is made through a local socket (empty ``host=`` in ``pretix.cfg``) and the name of the PostgreSQL user
  and the Linux user are identical.

  - Typically, you might run into this error if you accidentally execute ``python -m pretix`` commands as root instead
    of the ``pretix`` user.

- **Password authentication**, which requires a username and password and works over network connections. To force
  password authentication instead of peer authentication, set ``host=127.0.0.1`` in ``pretix.cfg``.

  - You can alter the password on a PostgreSQL shell using the command ``ALTER USER pretix WITH PASSWORD '***';``.
    When creating a user with the ``createuser`` command, pass option ``-P`` to set a new password.

  - Even with password authentication, PostgreSQL by default only allows local connections. To allow remote connections,
    you need to adjust both the ``listen_address`` configuration parameter as well as the ``pg_hba.conf`` file (see above
    for an example with the docker networking setup).

Database error: relation does not exist
"""""""""""""""""""""""""""""""""""""""

If you see an error like this::

    2023-04-17T19:20:47.744023Z ERROR Database error 42P01: relation "public.pretix_foobar" does not exist
    QUERY: ALTER TABLE public.pretix_foobar DROP CONSTRAINT IF EXISTS pretix_foobar_order_id_57e2cb41_fk_pretixbas CASCADE;
    2023-04-17T19:20:47.744023Z FATAL Failed to create the schema, see above.

The reason is most likely that in the past, you installed a pretix plugin that you no longer have installed. However,
the database still contains tables of that plugin. If you want to keep the data, reinstall the plugin and re-run the
``migrate`` step from above. If you want to get rid of the data, manually drop the table mentioned in the error message
from your MySQL database::

    # mysql -u root pretix
    mysql> DROP TABLE pretix_foobar;

Then, retry. You might see a new error message with a new table, which you can handle the same way.

Cleaning out a failed attempt
"""""""""""""""""""""""""""""

You might want to clean your PostgreSQL database before you try again after an error. You can do so like this::

    # sudo -u postgres psql pretix
    pretix=# DROP SCHEMA public CASCADE;
    pretix=# CREATE SCHEMA public;
    pretix=# ALTER SCHEMA public OWNER TO pretix;

``pgloader`` crashes with heap exhaustion error
"""""""""""""""""""""""""""""""""""""""""""""""

On some larger databases, we've seen ``pgloader`` crash with error messages similar to this::

    Heap exhausted during garbage collection: 16 bytes available, 48 requested.

Or this::

    2021-01-04T21:31:17.367000Z ERROR A SB-KERNEL::HEAP-EXHAUSTED-ERROR condition without bindings for heap statistics.  (If
    you did not expect to see this message, please report it.
    2021-01-04T21:31:17.382000Z ERROR The value
      NIL
    is not of type
      NUMBER
    when binding SB-KERNEL::X

The ``pgloader`` version distributed for Debian and Ubuntu is compiled with the ``SBCL`` compiler. If compiled with
``CCL``, these bugs go away. Unfortunately, it is pretty hard to compile ``pgloader`` manually with ``CCL``. If you
run into this, we therefore recommend using the docker container provided by the ``pgloader`` maintainers::

    sudo docker run --rm -v /tmp:/tmp --network host -it dimitri/pgloader:ccl.latest pgloader /tmp/pretix.load

As peer authentication is not available from inside the container, this requires you to use password-based authentication
in PostgreSQL (see above).


.. _PostgreSQL repositories: https://wiki.postgresql.org/wiki/Apt
