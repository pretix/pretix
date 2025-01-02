Basic concepts
==============

This page describes basic concepts and definition that you need to know to interact
with our Storefront API, such as authentication, pagination and similar definitions.

.. _`storefront-auth`:

Authentication
--------------

The storefront API requires authentication with an API key. You receive two kinds of API keys for the storefront API:
Publishable keys and private keys. Publishable keys should be used when your website directly connects to the API.
Private keys should be used only on server-to-server connections.

Localization
------------

The storefront API will return localized and translated strings in many cases if you set an ``Accept-Language`` header.
The selected locale will only be respected if it is active for the organizer or event in question.

.. _`storefront-compat`:

Compatibility
-------------

.. note::

   The storefront API is currently considered experimental and may change without notice.
   Once we declare the API stable, the following compatibility policy will apply.

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

Time Machine
------------

Just like our shop frontend, the API allows simulating responses at a different point in time using the
``X-Storefront-Time-Machine-Date`` header. This mechanism only works when the shop is in test mode.

Data types
----------

See :ref:`data types <rest-types>` of the REST API.
