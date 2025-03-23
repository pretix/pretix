Social Login Configuration
========================

This guide explains how to set up social login (SSO) options in pretix.

.. note:: Simply enabling the options in the interface is not enough. You need to create OAuth applications with the providers and configure them properly.

Supported Providers
------------------

pretix currently supports the following social login providers:

* Wikimedia
* GitHub
* Google

General Setup Process
--------------------

1. Create an OAuth application with the provider you want to integrate
2. Configure the redirect URL to point to your pretix installation
3. Enter the client ID and client secret in the pretix SSO settings
4. Enable the provider in pretix

Provider-Specific Instructions
-----------------------------

Wikimedia
~~~~~~~~~

1. Go to the `Wikimedia OAuth registration page <https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration/propose>`_
2. Create an OAuth2 application with these settings:
   - **Callback URL**: ``https://your-pretix-domain.com/control/global/settings/``
   - **Required scopes**: ``openid email profile``
3. Once approved, copy the **Client ID** and **Client Secret**
4. Enter them in the pretix SSO settings page

GitHub
~~~~~~

1. Go to `GitHub Developer Settings <https://github.com/settings/applications/new>`_
2. Create a new OAuth application:
   - **Application name**: Pretix (or your own name)
   - **Homepage URL**: ``https://your-pretix-domain.com``
   - **Authorization callback URL**: ``https://your-pretix-domain.com/control/global/settings/``
3. After creating the application, copy the **Client ID**
4. Generate a new client secret and copy the **Client Secret**
5. Enter them in the pretix SSO settings page

Google
~~~~~~

1. Go to the `Google API Console <https://console.developers.google.com/apis/credentials>`_
2. Create credentials → OAuth client ID:
   - **Application type**: Web application
   - **Name**: Pretix (or your own name)
   - **Authorized JavaScript origins**: ``https://your-pretix-domain.com``
   - **Authorized redirect URIs**: ``https://your-pretix-domain.com/control/global/settings/``
3. After creating, copy the **Client ID** and **Client Secret**
4. Enter them in the pretix SSO settings page

Troubleshooting
--------------

If login doesn't work after configuration:

* Verify that the callback URL is correct and matches exactly
* Check that the required scopes are properly configured
* Make sure both the client ID and secret are correctly entered
* Verify that you've enabled the provider in pretix settings

For more help, see the `GitHub issues <https://github.com/pretix/pretix/issues>`_ or ask on our community forums. 