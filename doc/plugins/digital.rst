Digital content
===============

The digital content plugin provides a HTTP API that allows you to create new digital content for your ticket holders,
such as live streams, videos, or material downloads.

Resource description
--------------------

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
===================================== ========================== =======================================================

Endpoints
---------

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
