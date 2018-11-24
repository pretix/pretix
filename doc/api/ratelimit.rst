.. _`rest-ratelimit`:

Rate limiting
=============

.. note:: This page only applies to the pretix Hosted service at pretix.eu. APIs of custom pretix installations do not
          enforce any rate limiting by default.

All authenticated requests to pretix' API are rate limited. If you exceed the limits, you will receive a response
with HTTP status code ``429 Too Many Requests``. This response will have a ``Retry-After`` header, containing the number
of seconds you are supposed to wait until you try again. We expect that all API clients respect this. If you continue
to burst requests after a ``429`` status code, we might get in touch with you or, in extreme cases, disable your API
access.

Currently, the following rate limits apply:



.. rst-class:: rest-resource-table

===================================== =================================================================================
Authentication method                 Rate limit
===================================== =================================================================================
:ref:`rest-deviceauth`                360 requests per minute per device
:ref:`rest-tokenauth`                 360 requests per minute per organizer account
:ref:`rest-oauth`                     360 requests per minute per combination of accessed organizer and OAuth application
Session authentication                *Not an officially supported authentication method for external access*
===================================== =================================================================================

If you require a higher rate limit, please get in touch at support@pretix.eu and tell us about your use case, we are
sure we can work something out.
