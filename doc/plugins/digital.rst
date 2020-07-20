Digital content
===============

URL interpolation and JWT authentication
----------------------------------------

In the simplest case, you can use the digital content module to point users to a specific piece of content on some
platform after their ticket purchase, or show them an embedded video or live stream. However, the full power of the
module can be utilized by passing additional information to the target system to automatically authenticate the user
or pre-fill some fields with their data. For example, you could use an URL like this::

    https://webinars.example.com/join?as={attendee_name}&userid={order_code}-{positionid}

While this is already useful, it does not provide much security – anyone could guess a valid combination for that URL.
Therefore, the module allows you to pass information as a `JSON Web Token`_, which isn't encrypted, but signed with a
shared secret such that nobody can create their own tokens or modify the contents. To use a token, set up a URL like this::

    https://webinars.example.com/join?with_token={token}

Additionally, you will need to set a JWT secret and a token template, either through the pretix interface or through the
API (see below). pretix currently only supports tokens signed with ``HMAC-SHA256`` (``HS256``). Your token template can contain
whatever JSON you'd like to pass on based on the same variables, for example::

    {
        "iss": "pretix.eu",
        "aud": "webinars.example.com",
        "user": {
            "id": "{order_code}-{positionid}",
            "product": "{product_id}",
            "variation": "{variation_id}",
            "name": "{attendee_name}"
        }
    }

Variables can only be used in strings inside the JSON structure.
pretix will automatically add an ``iat`` claim with the current timestamp and an ``exp`` claim with an expiration timestamp
based on your configuration.


List of variables
"""""""""""""""""

The following variables are currently supported:

.. rst-class:: rest-resource-table

=================================== ====================================================================
Variable                            Description
=================================== ====================================================================
``order_code``                      Order code (alphanumerical, unique per order, not per ticket)
``positionid``                      ID of the ticket within the order (integer, starting at 1)
``order_email``                     E-mail address of the ticket purchaser
``product_id``                      Internal ID of the purchased product
``product_variation``               Internal ID of the purchased product variation (or empty)
``attendee_name``                   Full name of the ticket holder (or empty)
``attendee_name_*``                 Name parts of the ticket holder, depending on configuration, e.g. ``attendee_name_given_name`` or ``attendee_name_family_name``
``attendee_email``                  E-mail address of the ticket holder (or empty)
``attendee_company``                Company of the ticket holder (or empty)
``attendee_street``                 Street of the ticket holder's address (or empty)
``attendee_zipcode``                ZIP code of the ticket holder's address (or empty)
``attendee_city``                   City of the ticket holder's address (or empty)
``attendee_country``                Country code of the ticket holder's address (or empty)
``attendee_state``                  State of the ticket holder's address (or empty)
``answer[XYZ]``                     Answer to the custom question with identifier ``XYZ``
``invoice_name``                    Full name of the invoice address (or empty)
``invoice_name_*``                  Name parts of the invoice address, depending on configuration, e.g. ``invoice_name_given_name`` or ``invoice_name_family_name``
``invoice_company``                 Company of the invoice address (or empty)
``invoice_street``                  Street of the invoice address (or empty)
``invoice_zipcode``                 ZIP code of the invoice address (or empty)
``invoice_city``                    City of the invoice address (or empty)
``invoice_country``                 Country code of the invoice address (or empty)
``invoice_state``                   State of the invoice address (or empty)
``meta_XYZ``                        Value of the event's ``XYZ`` meta property
``token``                           Signed JWT (only to be used in URLs, not in tokens)
=================================== ====================================================================


API Resource description
-------------------------

The digital content plugin provides a HTTP API that allows you to create new digital content for your ticket holders,
such as live streams, videos, or material downloads.

The digital content resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal content ID
title                                 multi-lingual string       The content title (required)
content_type                          string                     The type of content, valid values are ``webinar``, ``video``, ``livestream``, ``link``, ``file``
url                                   string                     The location of the digital content
description                           multi-lingual string       A public description of the item. May contain Markdown
                                                                 syntax and is not required.
available_from                        datetime                   The first date time at which this content will be shown
                                                                 (or ``null``).
available_until                       datetime                   The last date time at which this content will b e shown
                                                                 (or ``null``).
all_products                          boolean                    If ``true``, the content is available to all buyers of tickets for this event. The ``limit_products`` field is ignored in this case.
limit_products                        list of integers           List of product/item IDs. This content is only shown to buyers of these ticket types.
position                              integer                    An integer, used for sorting
subevent                              integer                    Date in an event series this content should be shown for. Should be ``null`` if this is not an event series or if this should be shown to all customers.
jwt_template                          string                     Template for JWT token generation
jwt_secret                            string                     Secret for JWT token generation
jwt_validity                          integer                    JWT validity in days
===================================== ========================== =======================================================

API Endpoints
-------------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/digitalcontents/

   Returns a list of all digital content configured for an event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/digitalcontents/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "count": 1,
        "next": null,
        "previous": null,
        "results": [
          {
            "id": 1,
            "subevent": null,
            "title": {
                "en": "Concert livestream"
            },
            "content_type": "link",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "description": {
                "en": "Watch our event live here on YouTube!"
            },
            "all_products": true,
            "limit_products": [],
            "available_from": "2020-03-22T23:00:00Z",
            "available_until": null,
            "position": 1
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or event does not exist **or** you have no permission to view it.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/digitalcontents/(id)/

   Returns information on one content item, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/digitalcontents/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "subevent": null,
        "title": {
            "en": "Concert livestream"
        },
        "content_type": "link",
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "description": {
            "en": "Watch our event live here on YouTube!"
        },
        "all_products": true,
        "limit_products": [],
        "available_from": "2020-03-22T23:00:00Z",
        "available_until": null,
        "position": 1
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the content to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event/content does not exist **or** you have no permission to view it.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/digitalcontents/

   Create a new digital content.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/digitalcontents/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 166

      {
        "subevent": null,
        "title": {
            "en": "Concert livestream"
        },
        "content_type": "link",
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "description": {
            "en": "Watch our event live here on YouTube!"
        },
        "all_products": true,
        "limit_products": [],
        "available_from": "2020-03-22T23:00:00Z",
        "available_until": null,
        "position": 1
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 2,
        "subevent": null,
        "title": {
            "en": "Concert livestream"
        },
        "content_type": "link",
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "description": {
            "en": "Watch our event live here on YouTube!"
        },
        "all_products": true,
        "limit_products": [],
        "available_from": "2020-03-22T23:00:00Z",
        "available_until": null,
        "position": 1
      }

   :param organizer: The ``slug`` field of the organizer to create new content for
   :param event: The ``slug`` field of the event to create new content for
   :statuscode 201: no error
   :statuscode 400: The content could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create digital contents.


.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/digitalcontents/(id)/

   Update a content. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/digitalcontents/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 34

      {
        "url": "https://mywebsite.com"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: text/javascript

      {
        "id": 2,
        "subevent": null,
        "title": {
            "en": "Concert livestream"
        },
        "content_type": "link",
        "url": "https://mywebsite.com",
        "description": {
            "en": "Watch our event live here on YouTube!"
        },
        "all_products": true,
        "limit_products": [],
        "available_from": "2020-03-22T23:00:00Z",
        "available_until": null,
        "position": 1
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the content to modify
   :statuscode 200: no error
   :statuscode 400: The content could not be modified due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event/content does not exist **or** you have no permission to change it.


.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/digitalcontents/(id)/

   Delete a digital content.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/digitalcontents/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the content to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event/content does not exist **or** you have no permission to change it

.. _JSON Web Token: https://en.wikipedia.org/wiki/JSON_Web_Token
