Item add-ons
============

Resource description
--------------------

With add-ons, you can specify products that can be bought as an addition to this specific product. For example, if you
host a conference with a base conference ticket and a number of workshops, you could define the workshops as add-ons to
the conference ticket. With this configuration, the workshops cannot be bought on their own but only in combination with
a conference ticket. You can here specify categories of products that can be used as add-ons to this product. You can
also specify the minimum and maximum number of add-ons of the given category that can or need to be chosen. The user can
buy every add-on from the category at most once. If an add-on product has multiple variations, only one of them can be
bought.
The add-ons resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the add-on
addon_category                        integer                    Internal ID of the item category the add-on can be
                                                                 chosen from.
min_count                             integer                    The minimal number of add-ons that need to be chosen.
max_count                             integer                    The maximal number of add-ons that can be chosen.
position                              integer                    An integer, used for sorting
price_included                        boolean                    Adding this add-on to the item is free
===================================== ========================== =======================================================

.. versionchanged:: 1.12

   This resource has been added.

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/items/(item)/addons/

   Returns a list of all add-ons for a given item.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/items/11/addons/ HTTP/1.1
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
            "id": 3,
            "addon_category": 1,
            "min_count": 0,
            "max_count": 10,
            "position": 0,
            "price_included": true
          },
          {
            "id": 4,
            "addon_category": 2,
            "min_count": 0,
            "max_count": 10,
            "position": 1,
            "price_included": true
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param item: The ``id`` field of the item to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event/item does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/items/(item)/addons/(id)/

   Returns information on one add-on, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/items/1/addons/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 3,
        "addon_category": 1,
        "min_count": 0,
        "max_count": 10,
        "position": 1,
        "price_included": true
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param item: The ``id`` field of the item to fetch
   :param id: The ``id`` field of the add-on to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/bigevents/events/sampleconf/items/1/addons/

   Creates a new add-on

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/(organizer)/events/(event)/items/(item)/addons/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content: application/json

      {
        "addon_category": 1,
        "min_count": 0,
        "max_count": 10,
        "position": 1,
        "price_included": true
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 3,
        "addon_category": 1,
        "min_count": 0,
        "max_count": 10,
        "position": 1,
        "price_included": true
      }

   :param organizer: The ``slug`` field of the organizer of the event/item to create a add-on for
   :param event: The ``slug`` field of the event to create a add-on for
   :param item: The ``id`` field of the item to create a add-on for
   :statuscode 201: no error
   :statuscode 400: The add-on could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/items/(item)/addon/(id)/

   Update an add-on. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   You can change all fields of the resource except the ``id`` field.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/items/1/addons/3/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "min_count": 0,
        "max_count": 10
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 3,
        "addon_category": 1,
        "min_count": 0,
        "max_count": 10,
        "position": 1,
        "price_included": true
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param item: The ``id`` field of the item to modify
   :param id: The ``id`` field of the add-on to modify
   :statuscode 200: no error
   :statuscode 400: The add-on could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to change this resource.

.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/items/(id)/addons/(id)/

   Delete an add-on.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/items/1/addons/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the item to modify
   :param id: The ``id`` field of the add-on to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to delete this resource.
