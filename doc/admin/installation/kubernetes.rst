.. highlight:: none

.. _`kubernetes`:

Kubernetes deployment using Helm
================================

This guide describes the installation of pretix on a Kubernetes cluster using Helm. Helm is a package manager for Kubernetes that allows you to define, install, and upgrade Kubernetes applications. 

.. warning:: The Helm charts are maintained by the community and not by the pretix core team. If you encounter any issues with the Helm charts, please report them to the maintainers of the Helm charts. The pretix core team can not provide support for Helm deployments. This deployment is not officially supported.

Requirements
------------

Please set up the following systems beforehand, we'll not explain them here:

* A Kubernetes cluster with Helm
* Kubectl configured to this cluster
* A SMTP server to send out mails, some third-party server you have credentials for

Knowledge of Kubernetes and Helm is adviced.

.. note:: Please, do not run pretix without HTTPS encryption. You'll handle user data and thanks to `Let's Encrypt`_
          SSL certificates can be obtained for free these days. We also *do not* provide support for HTTP-only
          installations except for evaluation purposes.


Data files
----------
The Helm chart creates a Persistant Volume Claim (PVC) to store the data files. You can configure the size of the PVC in the `values.yaml` file. The default size is 5Gi. The data files are stored in the `/data` directory in the pretix container.

You can change the `persistence` values in the `values.yaml` file to use a different storage class or to set your own size.

Configuration
-------------

It's recommended to read the values you can set in the helm chart. You can find the values in the `values.yaml` file in the pretix helm chart. You can also override these values by creating a `values.yaml` file and passing it to the helm install command.

You can find the values.yaml file in the pretix helm chart on `ArtifactHub`_.

The helm chart uses environment variables to set Pretix configuration. You can set these environment variables in the `values.yaml` file.


See :ref:`email configuration <mail-settings>` to learn more about configuring mail features.

Helm installation
-----------------

First of all, enable the Helm chart repository::

    $ helm repo add techwolf12 https://helm.techwolf12.nl/
    $ helm repo update

You can now either run the following command to install pretix with the default values::

    $ helm install pretix techwolf12/pretix

Or you can create a `values.yaml` file and pass it to the helm install command::
    
    $ helm install pretix techwolf12/pretix -f values.yaml

Ingress
-------

By default, the reverse proxy is disabled. You can enable it by setting the `ingress.enabled` value to `true` in the `values.yaml` file. You can also configure the ingress by setting the `ingress` values in the `values.yaml` file.


Next steps
----------

Yay, you are done! You should now be able to reach pretix at https://pretix.yourdomain.com/control/ if you setup an Ingress. 
If you didn't setup an Ingress, you can port-forward to the pretix service to access the pretix control panel:: 
    
        $ kubectl port-forward svc/pretix 8000:8000

Now, open your browser and go to http://localhost:8000/control/.

Log in as *admin@localhost* with a password of *admin*. Don't forget to change that password! Create an organizer first, then
create an event and start selling tickets!

You should probably read :ref:`maintainance` next.

.. _`kubernetes_updates`:

Updates
-------

.. warning:: While we try hard not to break things, **please perform a backup before every upgrade**.

Updates are fairly simple, but require at least a short downtime::

    $ helm upgrade pretix techwolf12/pretix --install

Restarting the service can take a few seconds, especially if the update requires changes to the database.
This will upgrade to the latest version, optionally you can also specify a specific version to upgrade to. Helm chart versions are the same as the Pretix versions.

Make sure to also read :ref:`update_notes` and the release notes of the version you are updating to. Pay special
attention to the "Runtime and server environment" section of all release notes between your current and new version. Also check `ArtifactHub`_ for any breaking changes in the Helm chart.

.. _`kubernetes_plugininstall`:

Install a plugin
----------------

To install a plugin, you need to build your own docker image. To do so, create a new directory and place a file
named ``Dockerfile`` in it. The Dockerfile could look like this (replace ``pretix-passbook`` with the plugins of your
choice)::

    FROM pretix/standalone:stable
    USER root
    RUN pip3 install pretix-passbook
    USER pretixuser
    RUN cd /pretix/src && make production

Then, go to that directory and build the image and push it to a registry of your choice::

    $ docker build . -t mypretix:version
    $ docker push mypretix:version

Now, you can use this image as values for the `image.repository` and `image.tag` values in the `values.yaml` file. Optionally, you can also set `image.pullSecrets` if you use a private registry.


Scaling up
----------

If you need to scale up your pretix installation, you can do so by running multiple instances of the pretix web and worker containers.

Setting this up is easy, set the `replicas.pretixWeb` and `replicas.pretixWorker` values in the `values.yaml` file to the number of replicas you want to run.

.. _Let's Encrypt: https://letsencrypt.org/
.. _pretix.eu: https://pretix.eu/
.. _ArtifactHub: https://artifacthub.io/packages/helm/techwolf12/pretix