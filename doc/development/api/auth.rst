.. highlight:: python
   :linenothreshold: 5

Pluggable authentication backends
=================================

Plugins can supply additional authentication backends. This is mainly useful in self-hosted installations
and allows you to use company-wide login mechanisms such as LDAP or OAuth for accessing pretix' backend.

Every authentication backend contains an implementation of the interface defined in ``pretix.base.auth.BaseAuthBackend``
(see below). Note that pretix authentication backends work differently than plain Django authentication backends.
Basically, three pre-defined flows are supported:

* Authentication mechanisms that rely on a **set of input parameters**, e.g. a username and a password. These can be
  implemented by supplying the ``login_form_fields`` property and a ``form_authenticate`` method.

* Authentication mechanisms that rely on **external sessions**, e.g. a cookie or a proxy HTTP header. These can be
  implemented by supplying a ``request_authenticate`` method.

* Authentication mechanisms that rely on **redirection**, e.g. to an OAuth provider. These can be implemented by
  supplying a ``authentication_url`` method and implementing a custom return view.

Authentication backends are *not* collected through a signal. Instead, they must explicitly be set through the
``auth_backends`` directive in the ``pretix.cfg`` :ref:`configuration file <config>`.

In each of these methods (``form_authenticate``, ``request_authenticate`` or your custom view) you are supposed to
either get an existing :py:class:`pretix.base.models.User` object from the database or create a new one. There are a
few rules you need to follow:

* You **MUST** only return users with the ``auth_backend`` attribute set to the ``identifier`` value of your backend.

* You **MUST** create new users with the ``auth_backend`` attribute set to the ``identifier`` value of your backend.

* Every user object **MUST** have an email address. Email addresses are globally unique. If the email address is
  already registered to a user who signs in through a different backend, you **SHOULD** refuse the login.

The backend interface
---------------------

.. class:: pretix.base.auth.BaseAuthBackend

   The central object of each backend is the subclass of ``BaseAuthBackend``.

   .. autoattribute:: identifier

      This is an abstract attribute, you **must** override this!

   .. autoattribute:: verbose_name

      This is an abstract attribute, you **must** override this!

   .. autoattribute:: login_form_fields

   .. autoattribute:: visible

   .. automethod:: form_authenticate

   .. automethod:: request_authenticate

   .. automethod:: authentication_url

Logging users in
----------------

If you return a user from ``form_authenticate`` or ``request_authenticate``, the system will handle everything else
for you correctly. However, if you use a redirection method and build a custom view to verify the login, we strongly
recommend that you use the following utility method to correctly set session values and enforce two-factor
authentication (if activated):

.. autofunction:: pretix.control.views.auth.process_login
