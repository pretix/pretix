.. highlight:: python
   :linenothreshold: 5

.. _`cookieconsent`:

Handling cookie consent
=======================

pretix includes an optional feature to handle cookie consent explicitly to comply with EU regulations.
If your plugin sets non-essential cookies or includes a third-party service that does so, you should
integrate with this feature.

Server-side integration
-----------------------

First, you need to declare that you are using non-essential cookies by responding to the following
signal:

.. automodule:: pretix.presale.signals
   :no-index:
   :members: register_cookie_providers

You are expected to return a list of ``CookieProvider`` objects instantiated from the following class:

.. class:: pretix.presale.cookies.CookieProvider

   .. py:attribute:: CookieProvider.identifier

      A short and unique identifier used to distinguish this cookie provider form others (required).

   .. py:attribute:: CookieProvider.provider_name

      A human-readable name of the entity of feature responsible for setting the cookie (required).

   .. py:attribute:: CookieProvider.usage_classes

      A list of enum values from the ``pretix.presale.cookies.UsageClass`` enumeration class, such as
      ``UsageClass.ANALYTICS``, ``UsageClass.MARKETING``, or ``UsageClass.SOCIAL`` (required).

   .. py:attribute:: CookieProvider.privacy_url

      A link to a privacy policy (optional).

Here is an example of such a receiver:

.. code-block:: python

   @receiver(register_cookie_providers)
   def recv_cookie_providers(sender, request, **kwargs):
       return [
           CookieProvider(
               identifier='google_analytics',
               provider_name='Google Analytics',
               usage_classes=[UsageClass.ANALYTICS],
           )
       ]

JavaScript-side integration
---------------------------

The server-side integration only causes the cookie provider to show up in the cookie dialog. You still
need to care about actually enforcing the consent state.

You can access the consent state through the ``window.pretix.cookie_consent`` variable. Whenever the
value changes, a ``pretix:cookie-consent:change`` event is fired on the ``document`` object.

The variable will generally have one of the following states:

.. rst-class:: rest-resource-table

================================================================ =====================================================
State                                                            Interpretation
================================================================ =====================================================
``pretix === undefined || pretix.cookie_consent === undefined``  Your JavaScript has loaded before the cookie consent
                                                                 script. Wait for the event to be fired, then try again,
                                                                 do not yet set a cookie.
``pretix.cookie_consent === null``                               The cookie consent mechanism has not been enabled. This
                                                                 usually means that you can set cookies however you like.
``pretix.cookie_consent[identifier] === undefined``              The cookie consent mechanism is loaded, but has no data
                                                                 on your cookie yet, wait for the event to be fired, do not
                                                                 yet set a cookie.
``pretix.cookie_consent[identifier] === true``                   The user has consented to your cookie.
``pretix.cookie_consent[identifier] === false``                  The user has actively rejected your cookie.
================================================================ =====================================================

If you are integrating e.g. a tracking provider with native cookie consent support such
as Facebook's Pixel, you can integrate it like this:

.. code-block:: javascript

     var consent = (window.pretix || {}).cookie_consent;
     if (consent !== null && !(consent || {}).facebook) {
         fbq('consent', 'revoke');
     }
     fbq('init', ...);
     document.addEventListener('pretix:cookie-consent:change', function (e) {
         fbq('consent', (e.detail || {}).facebook ? 'grant' : 'revoke');
     })

If you have a JavaScript function that you only want to load if consent for a specific ``identifier``
is given, you can wrap it like this:

.. code-block:: javascript

     var consent_identifier = "youridentifier";
     var consent = (window.pretix || {}).cookie_consent;
     if (consent === null || (consent || {})[consent_identifier] === true) {
         // Cookie consent tool is either disabled or consent is given
         addScriptElement(src);
         return;
     }

     // Either cookie consent tool has not loaded yet or consent is not given
     document.addEventListener('pretix:cookie-consent:change', function onChange(e) {
         var consent = e.detail || {};
         if (consent === null || consent[consent_identifier] === true) {
             addScriptElement(src);
             document.removeEventListener('pretix:cookie-consent:change', onChange);
         }
     })
