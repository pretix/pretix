Basic concepts
==============

This page describes basic concepts and definition that you need to know to interact
with pretix' REST API, such as authentication, pagination and similar definitions.

.. _`rest-auth`:

Authentication
--------------

If you're building an application for end users, we strongly recommend that you use our
:ref:`OAuth-based authentication progress <rest-oauth>`. However, for simpler needs, you
can also go with static API tokens that you can create on a per-team basis (see below).

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