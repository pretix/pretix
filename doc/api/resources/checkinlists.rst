Check-in lists
==============

Resource description
--------------------

You can create check-in lists that you can use e.g. at the entrance of your event to track who is coming and if they
actually bought a ticket.

You can create multiple check-in lists to separate multiple parts of your event, for example if you have separate
entries for multiple ticket types. Different check-in lists are completely independent: If a ticket shows up on two
lists, it is valid once on every list. This might be useful if you run a festival with festival passes that allow
access to every or multiple performances as well as tickets only valid for single performances.

The check-in list resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the check-in list
name                                  string                     The internal name of the check-in list
all_products                          boolean                    If ``True``, the check-in lists contains tickets of all products in this event. The ``limit_products`` field is ignored in this case.
limit_products                        list of integers           List of item IDs to include in this list.
subevent                              integer                    ID of the date inside an event series this list belongs to (or ``null``).
position_count                        integer                    Number of tickets that match this list (read-only).
checkin_count                         integer                    Number of check-ins performed on this list (read-only).
===================================== ========================== =======================================================

.. versionchanged:: 1.10

   This resource has been added.

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/checkinlists/

   Returns a list of all check-in lists within a given event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/checkinlists/ HTTP/1.1
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
            "name": "Default list",
            "checkin_count": 123,
            "position_count": 456,
            "all_products": true,
            "limit_products": [],
            "subevent": null
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query integer subevent: Only return check-in lists of the sub-event with the given ID
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/checkinlists/(id)/

   Returns information on one check-in list, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/checkinlists/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "name": "Default list",
        "checkin_count": 123,
        "position_count": 456,
        "all_products": true,
        "limit_products": [],
        "subevent": null
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the check-in list to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/checkinlists/

   Creates a new check-in list.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/checkinlists/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content: application/json

      {
        "name": "VIP entry",
        "all_products": false,
        "limit_products": [1, 2],
        "subevent": null
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 2,
        "name": "VIP entry",
        "checkin_count": 0,
        "position_count": 0,
        "all_products": false,
        "limit_products": [1, 2],
        "subevent": null
      }

   :param organizer: The ``slug`` field of the organizer of the event/item to create a list for
   :param event: The ``slug`` field of the event to create a list for
   :statuscode 201: no error
   :statuscode 400: The list could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/checkinlists/(id)/

   Update a check-in list. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   You can change all fields of the resource except the ``id`` field and the ``checkin_count`` and ``position_count``
   fields.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/checkinlists/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "name": "Backstage",
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 2,
        "name": "Backstage",
        "checkin_count": 23,
        "position_count": 42,
        "all_products": false,
        "limit_products": [1, 2],
        "subevent": null
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the list to modify
   :statuscode 200: no error
   :statuscode 400: The list could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to change this resource.

.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/checkinlist/(id)/

   Delete a check-in list. Note that this also deletes the information on all checkins performed via this list.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/checkinlist/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the check-in list to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to delete this resource.
