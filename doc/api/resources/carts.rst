.. _rest-carts:

Cart positions
==============

The API provides limited access to the cart position data model. This API currently only allows creating and deleting
cart positions to reserve quota.

Cart position resource
----------------------

The cart position resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the cart position
cart_id                               string                     Identifier of the cart this belongs to, needs to end
                                                                 in "@api" for API-created positions
datetime                              datetime                   Time of creation
expires                               datetime                   The cart position will expire at this time and no longer block quota
item                                  integer                    ID of the item
variation                             integer                    ID of the variation (or ``null``)
price                                 money (string)             Price of this position
attendee_name                         string                     Specified attendee name for this position (or ``null``)
attendee_name_parts                   object of strings          Composition of attendee name (i.e. first name, last name, …)
attendee_email                        string                     Specified attendee email address for this position (or ``null``)
voucher                               integer                    Internal ID of the voucher used for this position (or ``null``)
addon_to                              integer                    Internal ID of the position this position is an add-on for (or ``null``)
is_bundled                            boolean                    If ``addon_to`` is set, this shows whether this is a bundled product or an addon product
subevent                              integer                    ID of the date inside an event series this position belongs to (or ``null``)
answers                               list of objects            Answers to user-defined questions
├ question                            integer                    Internal ID of the answered question
├ answer                              string                     Text representation of the answer
├ question_identifier                 string                     The question's ``identifier`` field
├ options                             list of integers           Internal IDs of selected option(s)s (only for choice types)
└ option_identifiers                  list of strings            The ``identifier`` fields of the selected option(s)s
seat                                  objects                    The assigned seat (or ``null``)
├ id                                  integer                    Internal ID of the seat instance
├ name                                string                     Human-readable seat name
├ zone_name                           string                     Name of the zone the seat is in
├ row_name                            string                     Name/number of the row the seat is in
├ row_label                           string                     Additional label of the row (or ``null``)
├ seat_number                         string                     Number of the seat within the row
├ seat_label                          string                     Additional label of the seat (or ``null``)
└ seat_guid                           string                     Identifier of the seat within the seating plan
===================================== ========================== =======================================================

Cart position endpoints
-----------------------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/cartpositions/

   Returns a list of API-created cart positions.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/cartpositions/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json
      X-Page-Generated: 2017-12-01T10:00:00Z

      {
        "count": 1,
        "next": null,
        "previous": null,
        "results": [
          {
            "id": 1,
            "cart_id": "XwokV8FojQviD9jhtDzKvHFdlLRNMhlfo3cNjGbuK6MUTQDT@api",
            "item": 1,
            "variation": null,
            "price": "23.00",
            "attendee_name": null,
            "attendee_name_parts": {},
            "attendee_email": null,
            "voucher": null,
            "addon_to": null,
            "is_bundled": false,
            "subevent": null,
            "datetime": "2018-06-11T10:00:00Z",
            "expires": "2018-06-11T10:00:00Z",
            "includes_tax": true,
            "seat": null,
            "answers": []
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/cartpositions/(id)/

   Returns information on one cart position, identified by its internal ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/cartpositions/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "cart_id": "XwokV8FojQviD9jhtDzKvHFdlLRNMhlfo3cNjGbuK6MUTQDT@api",
        "item": 1,
        "variation": null,
        "price": "23.00",
        "attendee_name": null,
        "attendee_name_parts": {},
        "attendee_email": null,
        "voucher": null,
        "addon_to": null,
        "is_bundled": false,
        "subevent": null,
        "datetime": "2018-06-11T10:00:00Z",
        "expires": "2018-06-11T10:00:00Z",
        "includes_tax": true,
        "seat": null,
        "answers": []
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the position to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested cart position does not exist.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/cartpositions/

   Creates a new cart position.

   .. warning:: This endpoint is considered **experimental**. It might change at any time without prior notice.

   .. warning::

       This endpoint is intended for advanced users. It is not designed to be used to build your own shop frontend.
       There is a lot that it does not or can not do, and you will need to be careful using it.
       It allows to bypass many of the restrictions imposed when creating a cart through the
       regular shop.

       Specifically, this endpoint currently

       * does not validate if products are only to be sold in a specific time frame

       * does not validate if the event's ticket sales are already over or haven't started

       * does not validate constraints on add-on products at the moment

       * does not check or calculate prices but believes any prices you send

       * does not prevent you from buying items that can only be bought with a voucher

       * does not support file upload questions

       Note that more validation might be added in the future, so please do not rely on missing validation.

   You can supply the following fields of the resource:

   * ``cart_id`` (optional, needs to end in ``@api``)
   * ``item``
   * ``variation`` (optional)
   * ``price``
   * ``seat`` (The ``seat_guid`` attribute of a seat. Required when the specified ``item`` requires a seat, otherwise must be ``null``.)
   * ``attendee_name`` **or** ``attendee_name_parts`` (optional)
   * ``attendee_email`` (optional)
   * ``subevent`` (optional)
   * ``expires`` (optional)
   * ``includes_tax`` (optional, **deprecated**, do not use, will be removed)
   * ``sales_channel`` (optional)
   * ``voucher`` (optional, expect a voucher code)
   * ``addons`` (optional, expect a list of nested objects of cart positions)
   * ``bundled`` (optional, expect a list of nested objects of cart positions)
   * ``answers``

      * ``question``
      * ``answer``
      * ``options``

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/cartpositions/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "item": 1,
        "variation": null,
        "price": "23.00",
        "attendee_name_parts": {
          "given_name": "Peter",
          "family_name": "Miller"
        },
        "attendee_email": null,
        "answers": [
          {
            "question": 1,
            "answer": "23",
            "options": []
          }
        ],
        "addons": [
          {
            "item": 2,
            "variation": null,
          }
        ],
        "subevent": null
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      (Full cart position resource, see above, with additional nested objects "addons" and "bundled".)

   :param organizer: The ``slug`` field of the organizer of the event to create a position for
   :param event: The ``slug`` field of the event to create a position for
   :statuscode 201: no error
   :statuscode 400: The item could not be created due to invalid submitted data or lack of quota.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this
         order.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/cartpositions/bulk_create/

   Creates multiple new cart position. **This operation is deliberately not atomic, so each cart position can succeed
   or fail individually, so the response code of the response is not the only thing to look at!**

   .. warning:: This endpoint is considered **experimental**. It might change at any time without prior notice.

   .. warning:: The same limitations as with the regular creation endpoint apply.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/cartpositions/bulk_create/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      [
        {
          "item": 1,
          "variation": null,
          "price": "23.00",
          "attendee_name_parts": {
            "given_name": "Peter",
            "family_name": "Miller"
          },
          "attendee_email": null,
          "answers": [
            {
              "question": 1,
              "answer": "23",
              "options": []
            }
          ],
          "subevent": null
        },
        {
          "item": 1,
          "variation": null,
          "price": "23.00",
          "attendee_name_parts": {
            "given_name": "Maria",
            "family_name": "Miller"
          },
          "attendee_email": null,
          "answers": [
            {
              "question": 1,
              "answer": "23",
              "options": []
            }
          ],
          "subevent": null
        }
      ]

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "results": [
          {
            "success": true,
            "errors": null,
            "data": {
              "id": 1,
              ...
            },
          },
          {
            "success": "false",
            "errors": {
              "non_field_errors": ["There is not enough quota available on quota \"Tickets\" to perform the operation."]
            },
            "data": null
          }
        ]
      }

   :param organizer: The ``slug`` field of the organizer of the event to create positions for
   :param event: The ``slug`` field of the event to create positions for
   :statuscode 200: See response for success
   :statuscode 400: Your input could not be parsed
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this
         order.

.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/cartpositions/(id)/

   Deletes a cart position, identified by its internal ID.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/cartpositions/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept
      Content-Type: application/json

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the position to delete
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested cart position does not exist.
