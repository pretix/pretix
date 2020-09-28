.. _`rest-oauth`:

OAuth authentication / "Connect with pretix"
============================================

In addition to static tokens, pretix supports `OAuth2`_-based authentication starting with
pretix 1.16. This allows you to put a "Connect with pretix" button into your website or tool
that allows the user to easily set up a connection between the two systems.

If you haven't worked with OAuth before, have a look at the `OAuth2 Simplified`_ tutorial.

Registering an application
--------------------------

To use OAuth, you need to register your application with the pretix instance you want to connect to.
In order to do this, log in to your pretix account and go to your user settings. Click on "Authorized applications"
first and then on "Manage your own apps". From there, you can "Create a new application".

You should fill in a descriptive name of your application that allows users to recognize who you are. You also need to
give a list of fully-qualified URLs that users will be redirected to after a successful authorization. After you pressed
"Save", you will be presented with a client ID and a client secret. Please note them down and treat the client secret
like a password; it should not become available to your users.

Obtaining an authorization grant
--------------------------------

To authorize a new user, link or redirect them to the ``authorize`` endpoint, passing your client ID as a query
parameter. Additionally, you can pass a scope (currently either ``read``, ``write``, ``read write`` or ``profile``)
and an URL the user should be redirected to after successful or failed authorization. You also need to pass the
``response_type`` parameter with a value of ``code``. Example::

    https://pretix.eu/api/v1/oauth/authorize?client_id=lsLi0hNL0vk53mEdYjNJxHUn1PcO1R6wVg81dLNT&response_type=code&scope=read+write&redirect_uri=https://pretalx.com

To prevent CSRF attacks, you can also optionally pass a ``state`` parameter with a random string. Later, when
redirecting back to your application, we will pass the same ``state`` parameter back to you, so you can compare if they
match.

After the user granted or denied access, they will be redirected back either to the ``redirect_url`` you passed in the
query or to the first redirect URL configured in your application settings.

On successful registration, we will append the query parameter ``code`` to the URL containing an authorization code.
For example, we might redirect the user to this URL::

    https://pretalx.com/?code=eYBBf8gmeD4E01HLoj0XflqO4Lg3Cw&state=e3KCh9mfx07qxU4bRpXk

You will need this ``code`` parameter to perform the next step.

On a failed registration, a query string like ``?error=access_denied`` will be appended to the redirection URL.

.. note:: By default, the user is asked to give permission on every call to this URL. If you **only** request the
          ``profile`` scope, i.e. no access to organizer data, you can pass the ``approval_prompt=auto`` parameter
          to skip user interaction on subsequen calls.

Getting an access token
-----------------------

Using the ``code`` value you obtained above and your client ID, you can now request an access token that actually gives
access to the API. The ``token`` endpoint expects you to authenticate using `HTTP Basic authentication`_ using your client
ID as a username and your client secret as a password. You are also required to again supply the same ``redirect_uri``
parameter that you used for the authorization.

.. http:post:: /api/v1/oauth/token

   Request a new access token

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/oauth/token HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Authorization: Basic bHNMaTBoTkwwdms1M21FZFlqTkp4SFVuMVBjTzFSNndWZzgxZExOVDplSmpzZVA0UjJMN0hMcjBiS0p1b3BmbnJtT2cyY3NDeTdYaFVVZ0FoalhUU0NhZHhRTjk3cVNvMkpPaXlWTFpQOEozaTVQd1FVdFIwNUNycG5ac2Z0bXJjdmNTbkZ1SkFmb2ZsUTdZUDRpSjZNTWFYTHIwQ0FpNlhIRFJjV1Awcg==

      grant_type=authorization_code&code=eYBBf8gmeD4E01HLoj0XflqO4Lg3Cw&redirect_uri=https://pretalx.com

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "access_token": "i3ytqTSRWsKp16fqjekHXa4tdM4qNC",
        "expires_in": 86400,
        "token_type": "Bearer",
        "scope": "read write",
        "refresh_token": "XBK0r8z4A4TTeR9LyMUyU2AM5rqpXp"
      }

   :statuscode 200: no error
   :statuscode 401: Authentication failure


As you can see, you receive two types of tokens: One "access token", and one "refresh token". The access token is valid
for a day and can be used to actually access the API. The refresh token does not have an expiration date and can be used
to obtain a new access_token after a day, so you should make sure to store the access token safely if you need long-term
access.

Using the API with an access token
----------------------------------

You can supply a valid access token as a ``Bearer``-type token in the ``Authorization`` header to get API access.

.. sourcecode:: http
   :emphasize-lines: 3

       GET /api/v1/organizers/ HTTP/1.1
       Host: pretix.eu
       Authorization: Bearer i3ytqTSRWsKp16fqjekHXa4tdM4qNC

Refreshing an access token
--------------------------

You can obtain a new access token using your refresh token any time. This can be done using the same ``token`` endpoint
used to obtain the first access token above, but with a different set of parameters:

.. sourcecode:: http

  POST /api/v1/oauth/token HTTP/1.1
  Host: pretix.eu
  Accept: application/json, text/javascript
  Authorization: Basic bHNMaTBoTkwwdms1M21FZFlqTkp4SFVuMVBjTzFSNndWZzgxZExOVDplSmpzZVA0UjJMN0hMcjBiS0p1b3BmbnJtT2cyY3NDeTdYaFVVZ0FoalhUU0NhZHhRTjk3cVNvMkpPaXlWTFpQOEozaTVQd1FVdFIwNUNycG5ac2Z0bXJjdmNTbkZ1SkFmb2ZsUTdZUDRpSjZNTWFYTHIwQ0FpNlhIRFJjV1Awcg==

  grant_type=refresh_token&refresh_token=XBK0r8z4A4TTeR9LyMUyU2AM5rqpXp

The previous access token will instantly become invalid.

Revoking a token
----------------

If you don't need a token any more or if you believe it may have been compromised, you can use the ``revoke_token``
endpoint to revoke it.

.. http:get:: /api/v1/oauth/revoke_token

   Revoke an access or refresh token. If you revoke an access token, you can still create a new one using the refresh token. If you
   revoke a refresh token, the connected access token  will also be revoked.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/oauth/revoke_token HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Authorization: Basic bHNMaTBoTkwwdms1M21FZFlqTkp4SFVuMVBjTzFSNndWZzgxZExOVDplSmpzZVA0UjJMN0hMcjBiS0p1b3BmbnJtT2cyY3NDeTdYaFVVZ0FoalhUU0NhZHhRTjk3cVNvMkpPaXlWTFpQOEozaTVQd1FVdFIwNUNycG5ac2Z0bXJjdmNTbkZ1SkFmb2ZsUTdZUDRpSjZNTWFYTHIwQ0FpNlhIRFJjV1Awcg==

      token=XBK0r8z4A4TTeR9LyMUyU2AM5rqpXp

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

   :statuscode 200: no error
   :statuscode 401: Authentication failure

If you want to revoke your client secret, you can generate a new one in the list of your managed applications in the
pretix user interface.

Fetching the user profile
-------------------------

If you need the user's meta data, you can fetch it here:

.. http:get:: /api/v1/me

   Returns the profile of the authenticated user

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/me HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Authorization: Bearer i3ytqTSRWsKp16fqjekHXa4tdM4qNC

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "email": "admin@localhost",
        "fullname": "John Doe",
        "locale": "de",
        "is_staff": false,
        "timezone": "Europe/Berlin"
      }

   :statuscode 200: no error
   :statuscode 401: Authentication failure

.. _OAuth2: https://en.wikipedia.org/wiki/OAuth
.. _OAuth2 Simplified: https://aaronparecki.com/oauth-2-simplified/
.. _HTTP Basic authentication: https://en.wikipedia.org/wiki/Basic_access_authentication
