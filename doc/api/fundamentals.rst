Basic concepts
==============

This page describes basic concepts and definition that you need to know to interact
with pretix' REST API, such as authentication, pagination and similar definitions.

.. _`rest-auth`:

Authentication
--------------

To access the API, you need to present valid authentication credentials. pretix currently
supports the following authorization schemes:

* :ref:`rest-tokenauth`: This is the simplest way and recommended for server-side applications
  that interact with pretix without user interaction.
* :ref:`rest-oauth`: This is the recommended way to use if you write a third-party application
  that users can connect with their pretix account. It provides the best user experience, but
  requires user interaction and slightly more implementation effort.
* :ref:`rest-deviceauth`: This is the recommended way if you build apps or hardware devices that can
  connect to pretix, e.g. for processing check-ins or to sell tickets offline. It provides a way
  to uniquely identify devices and allows for a quick configuration flow inside your software.
* Authentication using browser sessions: This is used by the pretix web interface and it is *not*
  officially supported for use by third-party applications. It might change or be removed at any
  time without prior notice. If you use it, you need to comply with Django's `CSRF policies`_.

Permissions
-----------

The API follows pretix team based permissions model. Each organizer can have several teams
each with it's own set of permissions. Each team can have any number of API keys attached.

To access a given endpoint the team the API key belongs to needs to have the corresponding
permission for the organizer/event being accessed.

Possible permissions are:

* Can create events
* Can change event settings
* Can change product settings
* Can view orders
* Can change orders
* Can view vouchers
* Can change vouchers

.. _`rest-compat`:

Compatibility
-------------

We try to avoid any breaking changes to our API to avoid hassle on your end. If possible, we'll
build new features in a way that keeps all pre-existing API usage unchanged. In some cases,
this might not be possible or only possible with restrictions. In these case, any
backwards-incompatible changes will be prominently noted in the "Changes to the REST API"
section of our release notes. If possible, we will announce them multiple releases in advance.

We treat the following types of changes as *backwards-compatible* so we ask you to make sure
that your clients can deal with them properly:

* Support of new API endpoints
* Support of new HTTP methods for a given API endpoint
* Support of new query parameters for a given API endpoint
* New fields contained in API responses
* New possible values of enumeration-like fields
* Response body structure or message texts on failed requests (``4xx``, ``5xx`` response codes)

We treat the following types of changes as *backwards-incompatible*:

* Type changes of fields in API responses
* New required input fields for an API endpoint
* New required type for input fields of an API endpoint
* Removal of endpoints, API methods or fields

Pagination
----------

Most lists of objects returned by pretix' API will be paginated. The response will take
the form of:

.. sourcecode:: javascript

    {
        "count": 117,
        "next": "https://pretix.eu/api/v1/organizers/?page=2",
        "previous": null,
        "results": […],
    }

As you can see, the response contains the total number of results in the field ``count``.
The fields ``next`` and ``previous`` contain links to the next and previous page of results,
respectively, or ``null`` if there is no such page. You can use those URLs to retrieve the
respective page.

The field ``results`` contains a list of objects representing the first results. For most
objects, every page contains 50 results. You can specify a lower pagination size using the
``page_size`` query parameter, but no more than 50.

Conditional fetching
--------------------

If you pull object lists from pretix' APIs regularly, we ask you to implement conditional fetching
to avoid unnecessary data traffic. This is not supported on all resources and we currently implement
two different mechanisms for different resources, which is necessary because we can only obtain best
efficiency for resources that do not support deletion operations.

Object-level conditional fetching
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The :ref:`rest-orders` resource list contains an HTTP header called ``X-Page-Generated`` containing the
current time on the server in ISO 8601 format. On your next request, you can pass this header
(as is, without any modifications necessary) as the ``modified_since`` query parameter and you will receive
a list containing only objects that have changed in the time since your last request.

List-level conditional fetching
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If modification checks are not possible with this granularity, you can instead check for the full list.
In this case, the list of objects may contain a regular HTTP header ``Last-Modified`` with the date of the
last modification to any item of that resource. You can then pass this date back in your next request in the
``If-Modified-Since`` header. If the any object has changed in the meantime, you will receive back a full list
(if something it missing, this means the object has been deleted). If nothing happened, we'll send back a
``304 Not Modified`` return code.

This is currently implemented on the following resources:

* :ref:`rest-categories`
* :ref:`rest-items`
* :ref:`rest-questions`
* :ref:`rest-quotas`
* :ref:`rest-subevents`
* :ref:`rest-taxrules`

Errors
------

Error responses (of type 400-499) are returned in one of the following forms, depending on
the type of error. General errors look like:

.. sourcecode:: http

   HTTP/1.1 405 Method Not Allowed
   Content-Type: application/json
   Content-Length: 42

   {"detail": "Method 'DELETE' not allowed."}

Field specific input errors include the name of the offending fields as keys in the response:

.. sourcecode:: http

   HTTP/1.1 400 Bad Request
   Content-Type: application/json
   Content-Length: 94

   {"amount": ["A valid integer is required."], "description": ["This field may not be blank."]}

If you see errors of type ``429 Too Many Requests``, you should read our documentation on :ref:`rest-ratelimit`.

Data types
----------

All structured API responses are returned in JSON format using standard JSON data types such
as integers, floating point numbers, strings, lists, objects and booleans. Most fields can
be ``null`` as well.

The following table shows some data types that have no native JSON representation and how
we serialize them to JSON.

===================== ============================ ===================================
Internal pretix type  JSON representation          Examples
===================== ============================ ===================================
Datetime              String in ISO 8601 format    ``"2017-12-27T10:00:00Z"``
                      with timezone (normally UTC) ``"2017-12-27T10:00:00.596934Z"``,
                                                   ``"2017-12-27T10:00:00+02:00"``
Date                  String in ISO 8601 format    ``2017-12-27``
Multi-lingual string  Object of strings            ``{"en": "red", "de": "rot", "de_Informal": "rot"}``
Money                 String with decimal number   ``"23.42"``
Currency              String with ISO 4217 code    ``"EUR"``, ``"USD"``
Relative datetime     *either* String in ISO 8601  ``"2017-12-27T10:00:00.596934Z"``,
                      format *or* specification of ``"RELDATE/3/12:00:00/presale_start/"``
                      a relative datetime,
                      constructed from a number of
                      days before the base point,
                      a time of day, and the base
                      point.
Relative date         *either* String in ISO 8601  ``"2017-12-27"``,
                      format *or* specification of ``"RELDATE/3/-/presale_start/"``
                      a relative date,
                      constructed from a number of
                      days before the base point
                      and the base point.
File                  URL in responses, ``file:``  ``"https://…"``, ``"file:…"``
                      specifiers in requests
                      (see below).
Date range            *either* two dates separated ``2022-03-18/2022-03-23``, ``2022-03-18/``,
                      by ``/`` *or* the name of a  ``/2022-03-23``, ``week_this``, ``week_next``,
                      defined range.               ``month_this``
===================== ============================ ===================================

Query parameters
^^^^^^^^^^^^^^^^

Most list endpoints allow a filtering of the results using query parameters. In this case, booleans should be passed
as the string values ``true`` and ``false``.

If the ``ordering`` parameter is documented for a resource, you can use it to sort the result set by one of the allowed
fields. Prepend a ``-`` to the field name to reverse the sort order.


Idempotency
-----------

Our API supports an idempotency mechanism to make sure you can safely retry operations without accidentally performing
them twice. This is useful if an API call experiences interruptions in transit, e.g. due to a network failure, and you
do not know if it completed successfully.

To perform an idempotent request, add a ``X-Idempotency-Key`` header with a random string value (we recommend a version
4 UUID) to your request. If we see a second request with the same ``X-Idempotency-Key`` and the same ``Authorization``
and ``Cookie`` headers, we will not perform the action for a second time but return the exact same response instead.

Please note that this also goes for most error responses. For example, if we returned you a ``403 Permission Denied``
error and you retry with the same ``X-Idempotency-Key``, you will get the same error again, even if you were granted
permission in the meantime! This includes internal server errors on our side that might have been fixed in the meantime.

There are only the following exceptions to the rule:

* Responses with status code ``409 Conflict`` are not cached. If you send the request again, it will be executed as a
  new request, since these responses are intended to be retried.

* Rate-limited responses with status code ``429 Too Many Requests`` are not cached and you can safely retry them.

* Responses with status code ``500 Internal Server Error`` are not cached and you can retry them. This is not guaranteed
  to be safe in all theoretical cases,  but 500 by definition is an unforeseen situation and we need to have some way out.

* Responses with status code ``503 Service Unavailable`` are not cached and you can safely retry them.

If you send a request with an ``X-Idempotency-Key`` header that we have seen before but that has not yet received a
response, you will receive a response with status code ``409 Conflict`` and are asked to retry after five seconds.

We store idempotency keys for 24 hours, so you should never retry a request after a longer time period.

All ``POST``, ``PUT``, ``PATCH``, or ``DELETE`` api calls support idempotency keys. Adding an idempotency key to a
``GET``, ``HEAD``, or ``OPTIONS`` request has no effect.


File upload
-----------

In some places, the API supports working with files, for example when setting the picture of a product. In this case,
you will first need to make a separate request to our file upload endpoint:

.. sourcecode:: http

   POST /api/v1/upload HTTP/1.1
   Host: pretix.eu
   Authorization: Token e1l6gq2ye72thbwkacj7jbri7a7tvxe614ojv8ybureain92ocub46t5gab5966k
   Content-Type: image/png
   Content-Disposition: attachment; filename="logo.png"
   Content-Length: 1234

   <raw file content>

Note that the ``Content-Type`` and ``Content-Disposition`` headers are required. If the upload was successful, you will
receive a JSON response with the ID of the file:

.. sourcecode:: http

   HTTP/1.1 201 Created
   Content-Type: application/json

   {
     "id": "file:1cd99455-1ebd-4cda-b1a2-7a7d2a969ad1"
   }

You can then use this file ID in the request you want to use it in. File IDs are currently valid for 24 hours and can only
be used using the same authorization method and user that was used to upload them.

.. sourcecode:: http

   PATCH /api/v1/organizers/test/events/test/items/3/ HTTP/1.1
   Host: pretix.eu
   Content-Type: application/json

   {
     "picture": "file:1cd99455-1ebd-4cda-b1a2-7a7d2a969ad1"
   }


.. _CSRF policies: https://docs.djangoproject.com/en/1.11/ref/csrf/#ajax
