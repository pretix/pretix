.. _`rest-seats`:

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
product                               integer                    Internal ID of the product that is mapped to this seat
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

      GET /api/v1/organizers/bigevents/events/sampleconf/seats/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json

   **Example response**:

   .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
            "count": 500,
            "next": "https://pretix.eu/api/v1/organizers/bigevents/events/sampleconf/seats/?page=2",
            "previous": null,
            "results": [
                {
                    "id": 1633,
                    "subevent": null,
                    "zone_name": "Ground floor",
                    "row_name": "1",
                    "row_label": null,
                    "seat_number": "1",
                    "seat_label": null,
                    "seat_guid": "b9746230-6f31-4f41-bbc9-d6b60bdb3342",
                    "product": 104,
                    "blocked": false,
                    "orderposition": null,
                    "cartposition": null,
                    "voucher": 51
                },
                {
                    "id": 1634,
                    "subevent": null,
                    "zone_name": "Ground floor",
                    "row_name": "1",
                    "row_label": null,
                    "seat_number": "2",
                    "seat_label": null,
                    "seat_guid": "1d29fe20-8e1e-4984-b0ee-2773b0d07e07",
                    "product": 104,
                    "blocked": true,
                    "orderposition": 4321,
                    "cartposition": null,
                    "voucher": null
                },
                // ...
            ]
        }

   :query integer page: The page number in case of a multi-page result set, default is 1.
   :query string zone_name: Only show seats with the given zone_name.
   :query string row_name: Only show seats with the given row_name.
   :query string row_label: Only show seats with the given row_label.
   :query string seat_number: Only show seats with the given seat_number.
   :query string seat_label: Only show seats with the given seat_label.
   :query string seat_guid: Only show seats with the given seat_guid.
   :query boolean blocked: Only show seats with the given blocked status.
   :query boolean is_available: Only show seats that are (not) currently available.
   :query string expand: If you pass ``"orderposition"``, ``"cartposition"``, or ``"voucher"``, the respective field will be
                         shown as a nested value instead of just an ID. This requires permission to access that object.
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

        GET /api/v1/organizers/bigevents/events/sampleconf/seats/1634/?expand=orderposition HTTP/1.1
        Host: pretix.eu
        Accept: application/json

   **Example response**:

   .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
            "id": 1634,
            "subevent": null,
            "zone_name": "Ground floor",
            "row_name": "1",
            "row_label": null,
            "seat_number": "2",
            "seat_label": null,
            "seat_guid": "1d29fe20-8e1e-4984-b0ee-2773b0d07e07",
            "product": 104,
            "blocked": true,
            "orderposition": {
                "id": 134,
                "order": {
                    "code": "U0HW7",
                    "event": "sampleconf"
                },
                "positionid": 1,
                "item": 104,
                "variation": 59,
                "price": "60.00",
                "attendee_name": "",
                "attendee_name_parts": {
                    "_scheme": "given_family"
                },
                "company": null,
                "street": null,
                "zipcode": null,
                "city": null,
                "country": null,
                "state": null,
                "discount": null,
                "attendee_email": null,
                "voucher": null,
                "tax_rate": "0.00",
                "tax_value": "0.00",
                "secret": "4rfgp263jduratnsvwvy6cc6r6wnptbj",
                "addon_to": null,
                "subevent": null,
                "checkins": [],
                "downloads": [],
                "answers": [],
                "tax_rule": null,
                "pseudonymization_id": "ZSNYSG3URZ",
                "canceled": false,
                "valid_from": null,
                "valid_until": null,
                "blocked": null,
                "voucher_budget_use": null
            },
            "cartposition": null,
            "voucher": null
        }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param subevent_id: The ``id`` field of the subevent to fetch
   :param id: The ``id`` field of the seat to fetch
   :query string expand: If you pass ``"orderposition"``, ``"cartposition"``, or ``"voucher"``, the respective field will be
                         shown as a nested value instead of just an ID. This requires permission to access that object.
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

        PATCH /api/v1/organizers/bigevents/events/sampleconf/seats/1636/ HTTP/1.1
        Host: pretix.eu
        Accept: application/json, text/javascript
        Content-Type: application/json

        {
            "blocked": true
        }

   **Example response**:

   .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
            "id": 1636,
            "subevent": null,
            "zone_name": "Ground floor",
            "row_name": "1",
            "row_label": null,
            "seat_number": "4",
            "seat_label": null,
            "seat_guid": "6c0e29e5-05d6-421f-99f3-afd01478ecad",
            "product": 104,
            "blocked": true,
            "orderposition": null,
            "cartposition": null,
            "voucher": null
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


.. http:post:: /api/v1/organizers/(organizer)/events/(event)/seats/bulk_block/
.. http:post:: /api/v1/organizers/(organizer)/events/(event)/subevents/(id)/seats/bulk_block/

   Set the ``blocked`` attribute to ``true`` for a large number of seats at once.
   You can pass either a list of ``id`` values or a list of ``seat_guid`` values.
   You can pass up to 10,000 seats in one request.

   The endpoint will return an error if you pass a seat ID that does not exist.
   However, it will not return an error if one of the passed seats is already blocked or sold.

   **Example request**:

   .. sourcecode:: http

        PATCH /api/v1/organizers/bigevents/events/sampleconf/seats/bulk_block/ HTTP/1.1
        Host: pretix.eu
        Accept: application/json, text/javascript
        Content-Type: application/json

        {
            "ids": [12, 45, 56]
        }

   or

   .. sourcecode:: http

        PATCH /api/v1/organizers/bigevents/events/sampleconf/seats/bulk_block/ HTTP/1.1
        Host: pretix.eu
        Accept: application/json, text/javascript
        Content-Type: application/json

        {
            "seat_guids": ["6c0e29e5-05d6-421f-99f3-afd01478ecad", "c2899340-e2e7-4d05-8100-000a4b6d7cf4"]
        }

   **Example response**:

   .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {}

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param subevent_id: The ``id`` field of the subevent to modify
   :statuscode 200: no error
   :statuscode 400: The seat could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or event does not exist **or** you have no permission to change this resource.
   :statuscode 404: Seat does not exist; or the endpoint without subevent id was used for event with subevents, or vice versa.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/seats/bulk_unblock/
.. http:post:: /api/v1/organizers/(organizer)/events/(event)/subevents/(id)/seats/bulk_unblock/

   Set the ``blocked`` attribute to ``false`` for a large number of seats at once.
   You can pass either a list of ``id`` values or a list of ``seat_guid`` values.
   You can pass up to 10,000 seats in one request.

   The endpoint will return an error if you pass a seat ID that does not exist.
   However, it will not return an error if one of the passed seat is already unblocked or is sold.

   **Example request**:

   .. sourcecode:: http

        PATCH /api/v1/organizers/bigevents/events/sampleconf/seats/bulk_unblock/ HTTP/1.1
        Host: pretix.eu
        Accept: application/json, text/javascript
        Content-Type: application/json

        {
            "ids": [12, 45, 56]
        }

   or

   .. sourcecode:: http

        PATCH /api/v1/organizers/bigevents/events/sampleconf/seats/bulk_unblock/ HTTP/1.1
        Host: pretix.eu
        Accept: application/json, text/javascript
        Content-Type: application/json

        {
            "seat_guids": ["6c0e29e5-05d6-421f-99f3-afd01478ecad", "c2899340-e2e7-4d05-8100-000a4b6d7cf4"]
        }

   **Example response**:

   .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {}

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param subevent_id: The ``id`` field of the subevent to modify
   :statuscode 200: no error
   :statuscode 400: The seat could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or event does not exist **or** you have no permission to change this resource.
   :statuscode 404: Seat does not exist; or the endpoint without subevent id was used for event with subevents, or vice versa.
