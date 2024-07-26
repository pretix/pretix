.. _`rest-reusablemedia`:

Seats
=====

The seat resource represents the seats in a seating plan in a specific event or subevent.

Resource description
--------------------

The seat resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of this seat
subevent                              integer                    Internal ID of the subevent this seat belongs to
zone_name                             string                     Name of the zone the seat is in
row_name                              string                     Name/number of the row the seat is in
row_label                             string                     Additional label of the row (or ``null``)
seat_number                           string                     Number of the seat within the row
seat_label                            string                     Additional label of the seat (or ``null``)
seat_guid                             string                     Identifier of the seat within the seating plan
product                               integer                    Internal ID of the product that's mapped to this seat
blocked                               boolean                    Whether this seat is blocked manually.
orderposition                         integer / object           Internal ID of an order position reserving this seat.
cartposition                          integer / object           Internal ID of a cart position reserving this seat.
voucher                               integer / object           Internal ID of a voucher reserving this seat.
===================================== ========================== =======================================================

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/seats/
.. http:get:: /api/v1/organizers/(organizer)/events/(event)/subevents/(subevent_id)/seats/

   Returns a list of all seats in the specified event or subevent. Depending on whether the event has subevents, the
   according endpoint has to be used.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/demoevent/seats/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json

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
            ...TODO
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1.
   :query string zone_name: Only show seats with the given zone_name.
   :query string row_name: Only show seats with the given row_name.
   :query string row_label: Only show seats with the given row_label.
   :query string seat_number: Only show seats with the given seat_number.
   :query string seat_label: Only show seats with the given seat_label.
   :query string seat_guid: Only show seats with the given seat_guid.
   :query string blocked: Only show seats with the given blocked status.
   :query string expand: If you pass ``"orderposition"``, ``"cartposition"``, or ``"voucher"``, the respective field will be
                         shown as a nested value instead of just an ID.
                         The nested objects are identical to the respective resources, except that order positions
                         will have an attribute of the format ``"order": {"code": "ABCDE", "event": "eventslug"}`` to make
                         matching easier, and won't include the `seat` attribute, as that would be redundant.
                         The parameter can be given multiple times.
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param subevent_id: The ``id`` field of the subevent to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.
   :statuscode 404: Endpoint without subevent id was used for event with subevents, or vice versa.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/seats/(id)/
.. http:get:: /api/v1/organizers/(organizer)/events/(event)/subevents/(subevent_id)/seats/(id)/

   Returns information on one seat, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/demoevent/seats/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        ...TODO
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param subevent_id: The ``id`` field of the subevent to fetch
   :param id: The ``id`` field of the seat to fetch
   :query string expand: If you pass ``"orderposition"``, ``"cartposition"``, or ``"voucher"``, the respective field will be
                         shown as a nested value instead of just an ID.
                         The nested objects are identical to the respective resources, except that order positions
                         will have an attribute of the format ``"order": {"code": "ABCDE", "event": "eventslug"}`` to make
                         matching easier, and won't include the `seat` attribute, as that would be redundant.
                         The parameter can be given multiple times.
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.
   :statuscode 404: Seat does not exist; or the endpoint without subevent id was used for event with subevents, or vice versa.

.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/seats/(id)/
.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/subevents/(id)/seats/(id)/

   Update a seat.

   You can only change the ``blocked`` field.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/demoevent/seats/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: TODO

      {
        "blocked": true
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        ...TODO
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param subevent_id: The ``id`` field of the subevent to modify
   :param id: The ``id`` field of the seat to modify
   :statuscode 200: no error
   :statuscode 400: The seat could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or event does not exist **or** you have no permission to change this resource.
   :statuscode 404: Seat does not exist; or the endpoint without subevent id was used for event with subevents, or vice versa.
