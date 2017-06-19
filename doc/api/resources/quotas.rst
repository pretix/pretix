Quotas
======

Resource description
--------------------

Questions define how many times an item can be sold.
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
subevent                              integer                    ID of the sub-event this quota belongs to (or ``null``).
===================================== ========================== =======================================================


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
      Content-Type: text/javascript

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
            "subevent": null
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
      Content-Type: text/javascript

      {
        "id": 1,
        "name": "Ticket Quota",
        "size": 200,
        "items": [1, 2],
        "variations": [1, 4, 5, 7],
        "subevent": null
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the quota to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

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
      Content-Type: text/javascript

      {
        "available": true,
        "available_number": 419,
        "total_size": 1000,
        "pending_orders": 25,
        "paid_orders": 423,
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
