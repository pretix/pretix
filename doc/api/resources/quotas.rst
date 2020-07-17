.. _rest-quotas:

Quotas
======

Resource description
--------------------

Quotas define how many times an item can be sold.
The quota resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the quota
name                                  string                     The internal name of the quota
size                                  integer                    The size of the quota or ``null`` for unlimited
items                                 list of integers           List of item IDs this quota acts on.
variations                            list of integers           List of item variation IDs this quota acts on.
subevent                              integer                    ID of the date inside an event series this quota belongs to (or ``null``).
close_when_sold_out                   boolean                    If ``true``, the quota will "close" as soon as it is
                                                                 sold out once. Even if tickets become available again,
                                                                 they will not be sold unless the quota is set to open
                                                                 again.
closed                                boolean                    Whether the quota is currently closed (see above
                                                                 field).
release_after_exit                    boolean                    Whether the quota regains capacity as soon as some tickets
                                                                 have been scanned at an exit.
===================================== ========================== =======================================================

.. versionchanged:: 1.10

   The write operations ``POST``, ``PATCH``, ``PUT``, and ``DELETE`` have been added.

.. versionchanged:: 3.0

   The attributes ``close_when_sold_out`` and ``closed`` have been added.

.. versionchanged:: 3.10

   The attribute ``release_after_exit`` has been added.


Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/quotas/

   Returns a list of all quotas within a given event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/quotas/ HTTP/1.1
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
            "name": "Ticket Quota",
            "size": 200,
            "items": [1, 2],
            "variations": [1, 4, 5, 7],
            "subevent": null,
            "close_when_sold_out": false,
            "closed": false
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query string ordering: Manually set the ordering of results. Valid fields to be used are ``id`` and ``position``.
                           Default: ``position``
   :query integer subevent: Only return quotas of the sub-event with the given ID
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/quotas/(id)/

   Returns information on one quota, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/quotas/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "name": "Ticket Quota",
        "size": 200,
        "items": [1, 2],
        "variations": [1, 4, 5, 7],
        "subevent": null,
        "close_when_sold_out": false,
        "closed": false
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the quota to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/quotas/

   Creates a new quota

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/quotas/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "name": "Ticket Quota",
        "size": 200,
        "items": [1, 2],
        "variations": [1, 4, 5, 7],
        "subevent": null,
        "close_when_sold_out": false,
        "closed": false
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "name": "Ticket Quota",
        "size": 200,
        "items": [1, 2],
        "variations": [1, 4, 5, 7],
        "subevent": null,
        "close_when_sold_out": false,
        "closed": false
      }

   :param organizer: The ``slug`` field of the organizer of the event/item to create a quota for
   :param event: The ``slug`` field of the event to create a quota for
   :statuscode 201: no error
   :statuscode 400: The quota could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/quotas/(id)/

   Update a quota. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   You can change all fields of the resource except the ``id`` field.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/quotas/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "name": "New Ticket Quota",
        "size": 100,
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 2,
        "name": "New Ticket Quota",
        "size": 100,
        "items": [
          1,
          2
        ],
        "variations": [
          1,
          2
        ],
        "subevent": null,
        "close_when_sold_out": false,
        "closed": false
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the quota rule to modify
   :statuscode 200: no error
   :statuscode 400: The quota could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to change this resource.

.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/quota/(id)/

   Delete a quota. Note that if you delete a quota the items the quota acts on might no longer be available for sale.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/quotas/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the quotas to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to delete this resource.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/quotas/(id)/availability/

   Returns availability information on one quota, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/quotas/1/availability/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "available": true,
        "available_number": 419,
        "total_size": 1000,
        "pending_orders": 25,
        "paid_orders": 423,
        "exited_orders": 0,
        "cart_positions": 7,
        "blocking_vouchers": 126,
        "waiting_list": 0
    }

   Note that ``total_size`` and ``available_number`` are ``null`` in case of unlimited quotas.

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the quota to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
