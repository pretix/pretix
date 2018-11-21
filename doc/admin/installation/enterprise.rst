.. highlight:: none

Installing pretix Enterprise plugins
====================================

If you want to use a feature of pretix that is part of our commercial offering pretix Enterprise, you need to follow
some extra steps. Installation works similar to normal pretix plugins, but involves a few extra steps.

Buying the license
------------------

To obtain a license, please get in touch at sales@pretix.eu. Please let us know how many tickets you roughly intend
to sell per year and how many servers you want to use the plugin on. We recommend having a look at our `price list`_
first.


Manual installation
-------------------

First, generate an SSH key for the system user that you install pretix as. In our tutorial, that would be the user
``pretix``. Choose an empty passphrase::

    # su pretix
    $ ssh-keygen
    Generating public/private rsa key pair.
    Enter file in which to save the key (/var/pretix/.ssh/id_rsa):
    Enter passphrase (empty for no passphrase):
    Enter same passphrase again:
    Your identification has been saved in /var/pretix/.ssh/id_rsa.
    Your public key has been saved in /var/pretix/.ssh/id_rsa.pub.

Next, send the content of the *public* key to your sales representative at pretix::

    $ cat /var/pretix/.ssh/id_rsa.pub
    ssh-rsa AAAAB3N...744HZawHlD pretix@foo

After we configured your key in our system, you can install the plugin directly using ``pip`` from the URL we told
you, for example::

    $ source /var/pretix/venv/bin/activate
    (venv)$ pip3 install -U "git+ssh://git@code.rami.io:10022/pretix/pretix-slack.git@stable#egg=pretix-slack"
    (venv)$ python -m pretix migrate
    (venv)$ python -m pretix rebuild
    # systemctl restart pretix-web pretix-worker

Docker installation
-------------------

To install a plugin, you need to build your own docker image. To do so, create a new directory to work in. As a first
step, generate a new SSH key in that directory to use for authentication with us::

    $ cd /home/me/mypretixdocker
    $ ssh-keygen -N "" -f id_pretix_enterprise

Next, send the content of the *public* key to your sales representative at pretix::

    $ cat id_pretix_enterprise.pub
    ssh-rsa AAAAB3N...744HZawHlD pretix@foo

After we configured your key in our system, you can add a ``Dockerfile`` in your directory that includes the newly
generated key and installs the plugin from the URL we told you::

    FROM pretix/standalone:stable
    USER root
    COPY id_pretix_enterprise /root/.ssh/id_rsa
    COPY id_pretix_enterprise.pub /root/.ssh/id_rsa.pub
    RUN chmod -R 0600 /root/.ssh && \
        mkdir -p /etc/ssh && \
        ssh-keyscan -t rsa -p 10022 code.rami.io >> /root/.ssh/known_hosts && \
        echo StrictHostKeyChecking=no >> /root/.ssh/config && \
        pip3 install -Ue "git+ssh://git@code.rami.io:10022/pretix/pretix-slack.git@stable#egg=pretix-slack" && \
        cd /pretix/src && \
        sudo -u pretixuser make production
    USER pretixuser

Then, build the image for docker::

    $ docker build -t mypretix

You can now use that image ``mypretix`` instead of ``pretix/standalone:stable`` in your ``/etc/systemd/system/pretix.service``
service file. Be sure to re-build your custom image after you pulled ``pretix/standalone`` if you want to perform an
update to a new version of pretix.

.. _price list: https://pretix.eu/about/en/pricing
