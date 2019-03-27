Item variations
===============

Resource description
--------------------

Variations of items can be use for products (items) that are available in different sizes, colors or other variations
of the same product.
The variations resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the variation
default_price                         money (string)             The price set directly for this variation or ``null``
price                                 money (string)             The price used for this variation. This is either the
                                                                 same as ``default_price`` if that value is set or equal
                                                                 to the item's ``default_price`` (read-only).
active                                boolean                    If ``false``, this variation will not be sold or shown.
description                           multi-lingual string       A public description of the variation. May contain
                                                                 Markdown syntax or can be ``null``.
position                              integer                    An integer, used for sorting
===================================== ========================== =======================================================

.. versionchanged:: 1.12

   This resource has been added.

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/items/(item)/variations/

   Returns a list of all variations for a given item.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/items/11/variations/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "count": 2,
        "next": null,
        "previous": null,
        "results": [
          {
            "id": 1,
            "value": {
              "en": "S"
            },
            "active": true,
            "description": {
              "en": "Test2"
            },
            "position": 0,
            "default_price": "223.00",
            "price": 223.0
          },
          {
            "id": 3,
            "value": {
              "en": "L"
            },
            "active": true,
            "description": {},
            "position": 1,
            "default_price": null,
            "price": 15.0
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query boolean active: If set to ``true`` or ``false``, only items with this value for the field ``active`` will be
                          returned.
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param item: The ``id`` field of the item to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event/item does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/items/(item)/variations/(id)/

   Returns information on one variation, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/items/1/variations/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 3,
        "value": {
              "en": "Student"
        },
        "default_price": "10.00",
        "price": "10.00",
        "active": true,
        "description": null,
        "position": 0
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param item: The ``id`` field of the item to fetch
   :param id: The ``id`` field of the variation to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/items/(item)/variations/

   Creates a new variation

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/items/1/variations/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content: application/json

      {
        "value": {"en": "Student"},
        "default_price": "10.00",
        "active": true,
        "description": null,
        "position": 0
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "value": {"en": "Student"},
        "default_price": "10.00",
        "price": "10.00",
        "active": true,
        "description": null,
        "position": 0
      }

   :param organizer: The ``slug`` field of the organizer of the event/item to create a variation for
   :param event: The ``slug`` field of the event to create a variation for
   :param item: The ``id`` field of the item to create a variation for
   :statuscode 201: no error
   :statuscode 400: The variation could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/items/(item)/variations/(id)/

   Update a variation. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   You can change all fields of the resource except the ``id`` and the ``price`` field.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/items/1/variations/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "active": false,
        "position": 1
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "value": {"en": "Student"},
        "default_price": "10.00",
        "price": "10.00",
        "active": false,
        "description": null,
        "position": 1
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the item to modify
   :param id: The ``id`` field of the variation to modify
   :statuscode 200: no error
   :statuscode 400: The variation could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to change this resource.

.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/items/(id)/variations/(id)/

   Delete a variation.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/items/1/variations/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the item to modify
   :param id: The ``id`` field of the variation to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to delete this resource.
