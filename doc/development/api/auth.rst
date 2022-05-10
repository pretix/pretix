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

For security reasons, authentication backends are *not* automatically discovered through a signal. Instead, they must
explicitly be set through the ``auth_backends`` directive in the ``pretix.cfg`` :ref:`configuration file <config>`.

In each of these methods (``form_authenticate``, ``request_authenticate``, or your custom view) you are supposed to
use ``User.objects.get_or_create_for_backend`` to get a :py:class:`pretix.base.models.User` object from the database
or create a new one.

There are a few rules you need to follow:

* You **MUST** have some kind of identifier for a user that is globally unique and **SHOULD** never change, even if the
  user's name or email address changes. This could e.g. be the ID of the user in an external database. The identifier
  must not be longer than 190 characters. If you worry your backend might generated longer identifiers, consider
  using a hash function to trim them to a constant length.

* You **SHOULD** not allow users created by other authentication backends to log in through your code, and you **MUST**
  only create, modify or return users with ``auth_backend`` set to your backend.

* Every user object **MUST** have an email address. Email addresses are globally unique. If the email address is
  already registered to a user who signs in through a different backend, you **SHOULD** refuse the login.

``User.objects.get_or_create_for_backend`` will follow these rules for you automatically. It works like this:

.. autoclass:: pretix.base.models.auth.UserManager
   :members: get_or_create_for_backend

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

A custom view that is called after a redirect from an external identity provider could look like this::

   from django.contrib import messages
   from django.shortcuts import redirect
   from django.urls import reverse

   from pretix.base.models import User
   from pretix.base.models.auth import EmailAddressTakenError
   from pretix.control.views.auth import process_login


   def return_view(request):
       # Verify validity of login with the external provider's API
       api_response = my_verify_login_function(
           code=request.GET.get('code')
       )

       try:
           u = User.objects.get_or_create_for_backend(
               'my_backend_name',
               api_response['userid'],
               api_response['email'],
               set_always={
                   'fullname': '{} {}'.format(
                       api_response.get('given_name', ''),
                       api_response.get('family_name', ''),
                   ),
               },
               set_on_creation={
                   'locale': api_response.get('locale').lower()[:2],
                   'timezone': api_response.get('zoneinfo', 'UTC'),
               }
           )
       except EmailAddressTakenError:
           messages.error(
               request, _('We cannot create your user account as a user account in this system '
                          'already exists with the same email address.')
           )
           return redirect(reverse('control:auth.login'))
       else:
           return process_login(request, u, keep_logged_in=False)
