Basic concepts
==============

This page describes basic concepts and definition that you need to know to interact
with pretix' REST API, such as authentication, pagination and similar definitions.

.. _`rest-auth`:

Obtaining an API token
----------------------

To authenticate your API requests, you need to obtain an API token. You can create a
token in the pretix web interface on the level of organizer teams. Create a new team
or choose an existing team that has the level of permissions the token should have and
create a new token using the form below the list of team members:

.. image:: img/token_form.png
   :class: screenshot

You can enter a description for the token to distinguish from other tokens later on.
Once you click "Add", you will be provided with an API token in the success message.
Copy this token, as you won't be able to retrieve it again.

.. image:: img/token_success.png
   :class: screenshot

Authentication
--------------

You need to include the API token with every request to pretix' API in the ``Authorization`` header
like the following:

.. sourcecode:: http
   :emphasize-lines: 3

   GET /api/v1/organizers/ HTTP/1.1
   Host: pretix.eu
   Authorization: Token e1l6gq2ye72thbwkacj7jbri7a7tvxe614ojv8ybureain92ocub46t5gab5966k

.. note:: The API currently also supports authentication via browser sessions, i.e. the
          same way that you authenticate with pretix when using the browser interface.
          Using this type of authentication is *not* officially supported for use by
          third-party clients and might change or be removed at any time. We plan on
          adding OAuth2 support in the future for user-level authentication. If you want
          to use session authentication, be sure to comply with Django's `CSRF policies`_.

Compatibility
-------------

We currently see pretix' API as a beta-stage feature. We therefore do not give any guarantees
for compatibility between feature releases of pretix (such as 1.5 and 1.6). However, as always,
we try not to break things when we don't need to. Any backwards-incompatible changes will be
prominently noted in the release notes.

We treat the following types of changes as *backwards-compatible* so we ask you to make sure
that your clients can deal with them properly:

* Support of new API endpoints
* Support of new HTTP methods for a given API endpoint
* Support of new query parameters for a given API endpoint
* New fields contained in API responses

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
objects, every page contains 50 results.

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
===================== ============================ ===================================

Query parameters
^^^^^^^^^^^^^^^^

Most list endpoints allow a filtering of the results using query parameters. In this case, booleans should be passed
as the string values ``true`` and ``false``.

If the ``ordering`` parameter is documented for a resource, you can use it to sort the result set by one of the allowed
fields. Prepend a ``-`` to the field name to reverse the sort order.

.. _CSRF policies: https://docs.djangoproject.com/en/1.11/ref/csrf/#ajax