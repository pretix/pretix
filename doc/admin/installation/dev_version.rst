.. highlight:: none

Installing a development version
================================

If you want to use a feature of pretix that is not yet contained in the last monthly release, you can also
install a development version with pretix.

.. warning:: When in production, we strongly recommend only installing released versions. Development versions might
             be broken, incompatible to plugins, or in rare cases incompatible to upgrade later on.


Manual installation
-------------------

You can use ``pip`` to update pretix directly to the development branch. Then, upgrade as usual::

    $ source /var/pretix/venv/bin/activate
    (venv)$ pip3 install -U "git+https://github.com/pretix/pretix.git#egg=pretix&subdirectory=src"
    (venv)$ python -m pretix migrate
    (venv)$ python -m pretix rebuild
    (venv)$ python -m pretix updatestyles
    # systemctl restart pretix-web pretix-worker

Docker installation
-------------------

To use the latest development version with Docker, first pull it from Docker Hub::

    $ docker pull pretix/standalone:latest


Then change your ``/etc/systemd/system/pretix.service`` file to use the ``:latest`` tag instead of ``:stable`` as well
and upgrade as usual::

    $ systemctl restart pretix.service
    $ docker exec -it pretix.service pretix upgrade
