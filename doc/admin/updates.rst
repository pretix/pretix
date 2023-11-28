.. _`update_notes`:

Update notes
============

pretix receives regular feature and bugfix updates and we highly encourage you to always update to
the latest version for maximum quality and security. Updates are announces on our `blog`_. There are
usually 10 feature updates in a year, so you can expect a new release almost every month.

Pure bugfix releases are only issued in case of very critical bugs or security vulnerabilities. In these
case, we'll publish bugfix releases for the last three stable release branches.

Compatibility to plugins and in very rare cases API clients may break. For in-depth details on the
API changes of every version, please refer to the release notes published on our blog.

Upgrade steps
-------------

For the actual upgrade, you can usually just follow the steps from the installation guide for :ref:`manual installations <manual_updates>`
or :ref:`docker installations <docker_updates>` respectively.
Generally, it is always strongly recommended to perform a :ref:`backup <backups>` first.
It is possible to skip versions during updates, although we recommend not skipping over major version numbers
(i.e. if you want to go from 2.4 to 4.4, first upgrade to 3.0, then upgrade to 4.0, then to 4.4).

In addition to these standard update steps, the following list issues steps that should be taken when you upgrade
to specific versions for pretix. If you're skipping versions, please read the instructions for every version in
between as well.

Upgrade to 3.17.0 or newer
""""""""""""""""""""""""""

pretix 3.17 introduces a dependency on ``nodejs``, so you should install it on your system::

    # apt install nodejs npm

Upgrade to 4.4.0 or newer
"""""""""""""""""""""""""

pretix 4.4 introduces a new data structure to store historical financial data. If you already have existing
data in your database, you will need to back-fill this data or you might get incorrect reports! This is not
done automatically as part of the usual update steps since it can take a while on large databases and you might
want to do it in parallel while the system is already running again. Please execute the following command::

    (venv)$ python -m pretix create_order_transactions

Or, with a docker installation::

    $ docker exec -it pretix.service pretix create_order_transactions

Upgrade to 2023.6.0 or newer
""""""""""""""""""""""""""""

MariaDB and MySQL are no longer supported.

Upgrade to 2023.8.0 or newer
""""""""""""""""""""""""""""

PostgreSQL 11 is now required.

Upgrade to 2023.9.0 or newer
""""""""""""""""""""""""""""

This release includes a migration that changes the `id` column of all core database tables from `integer`
to `bigint`. If you have a large database, the migration step of the upgrade might take significantly longer than
usual, so plan the update accordingly.

The default value for the `registration` setting in `pretix.cfg` has changed to `false`.

Upgrade to 2023.10.0 or newer
"""""""""""""""""""""""""""""

This release includes a migration that changes retroactively fills an `organizer` column in the table
`pretixbase_logentry`. If you have a large database, the migration step of the upgrade might take significantly
longer than usual, so plan the update accordingly.

.. _blog: https://pretix.eu/about/en/blog/
