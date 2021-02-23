Item bundles
============

Resource description
--------------------

With bundles, you can specify products that are included within other products. There are two premier use cases of this:

* Package discounts. For example, you could offer a discounted package that includes three tickets but can only be
  bought as a whole. With a bundle including three times the usual product, the package will automatically pull three
  sub-items into the cart, making sure of correct quota calculation and issuance of the correct number of tickets.

* Tax splitting. For example, if your conference ticket includes a part that is subject to different taxation and that
  you need to put on the invoice separately. When you putting a "designated price" on a bundled sub-item, pretix will
  use that price to show a split taxation.

The bundles resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the bundling configuration
bundled_item                          integer                    Internal ID of the item that is included.
bundled_variation                     integer                    Internal ID of the variation of the item (or ``null``).
count                                 integer                    Number of items included
designated_price                      money (string)             Designated price of the bundled product. This will be
                                                                 used to split the price of the base item e.g. for mixed
                                                                 taxation. This is not added to the price.
===================================== ========================== =======================================================

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/items/(item)/bundles/

   Returns a list of all bundles for a given item.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/items/11/bundles/ HTTP/1.1
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
            "bundled_item": 3,
            "bundled_variation": null,
            "count": 1,
            "designated_price": "0.00"
          },
          {
            "id": 3,
            "bundled_item": 3,
            "bundled_variation": null,
            "count": 2,
            "designated_price": "1.50"
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

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/items/(item)/bundles/(id)/

   Returns information on one bundle configuration, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/items/1/bundles/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 3,
        "bundled_item": 3,
        "bundled_variation": null,
        "count": 2,
        "designated_price": "1.50"
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param item: The ``id`` field of the item to fetch
   :param id: The ``id`` field of the bundle to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/bigevents/events/sampleconf/items/1/bundles/

   Creates a new bundle configuration

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/(organizer)/events/(event)/items/(item)/bundles/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "bundled_item": 3,
        "bundled_variation": null,
        "count": 2,
        "designated_price": "1.50"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 3,
        "bundled_item": 3,
        "bundled_variation": null,
        "count": 2,
        "designated_price": "1.50"
      }

   :param organizer: The ``slug`` field of the organizer of the event/item to create a bundle-configuration for
   :param event: The ``slug`` field of the event to create a bundle configuration for
   :param item: The ``id`` field of the item to create a bundle configuration for
   :statuscode 201: no error
   :statuscode 400: The bundle could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/items/(item)/bundles/(id)/

   Update a bundle configuration. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all
   fields of the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields
   that you want to change.

   You can change all fields of the resource except the ``id`` field.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/items/1/bundles/3/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "count": 2
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 3,
        "bundled_item": 3,
        "bundled_variation": null,
        "count": 2,
        "designated_price": "1.50"
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param item: The ``id`` field of the item to modify
   :param id: The ``id`` field of the bundle to modify
   :statuscode 200: no error
   :statuscode 400: The bundle configuration could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to change this resource.

.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/items/(id)/bundles/(id)/

   Delete a bundle configuration.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/items/1/bundles/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the item to modify
   :param id: The ``id`` field of the bundle to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to delete this resource.
