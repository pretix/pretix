.. spelling::

   geo
   lat
   lon

.. _rest-subevents:

Event series dates / Sub-events
===============================

Resource description
--------------------

Events can represent whole event series if the ``has_subevents`` property of the event is active.
In this case, many other resources are additionally connected to an event date (also called sub-event).
The sub-event resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the sub-event
name                                  multi-lingual string       The sub-event's full name
event                                 string                     The slug of the parent event
active                                boolean                    If ``true``, the sub-event ticket shop is publicly
                                                                 available.
is_public                             boolean                    If ``true``, the sub-event ticket shop is publicly
                                                                 shown in lists.
date_from                             datetime                   The sub-event's start date
date_to                               datetime                   The sub-event's end date (or ``null``)
date_admission                        datetime                   The sub-event's admission date (or ``null``)
presale_start                         datetime                   The sub-date at which the ticket shop opens (or ``null``)
presale_end                           datetime                   The sub-date at which the ticket shop closes (or ``null``)
location                              multi-lingual string       The sub-event location (or ``null``)
geo_lat                               float                      Latitude of the location (or ``null``)
geo_lon                               float                      Longitude of the location (or ``null``)
item_price_overrides                  list of objects            List of items for which this sub-event overrides the
                                                                 default price
├ item                                integer                    The internal item ID
└ price                               money (string)             The price or ``null`` for the default price
variation_price_overrides             list of objects            List of variations for which this sub-event overrides
                                                                 the default price
├ variation                           integer                    The internal variation ID
└ price                               money (string)             The price or ``null`` for the default price
meta_data                             object                     Values set for organizer-specific meta data parameters.
seating_plan                          integer                    If reserved seating is in use, the ID of a seating
                                                                 plan. Otherwise ``null``.
seat_category_mapping                 object                     An object mapping categories of the seating plan
                                                                 (strings) to items in the event (integers or ``null``).
===================================== ========================== =======================================================

.. versionchanged:: 1.7

   The ``meta_data`` field has been added.

.. versionchanged:: 2.1

   The ``event`` field has been added, together with filters on the list of dates and an organizer-level list.

.. versionchanged:: 2.6
   The write operations ``POST``, ``PATCH``, ``PUT``, and ``DELETE`` have been added.

.. versionchanged:: 2.7

   The attribute ``is_public`` has been added.

.. versionchanged:: 3.0

   The attributes ``seating_plan`` and ``seat_category_mapping`` have been added.

.. versionchanged:: 3.3

   The attributes ``geo_lat`` and ``geo_lon`` have been added.

Endpoints
---------

.. versionchanged:: 3.3

    The sub-events resource can now be filtered by meta data attributes.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/subevents/

   Returns a list of all sub-events of an event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/subevents/ HTTP/1.1
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
            "name": {"en": "First Sample Conference"},
            "event": "sampleconf",
            "active": false,
            "is_public": true,
            "date_from": "2017-12-27T10:00:00Z",
            "date_to": null,
            "date_admission": null,
            "presale_start": null,
            "presale_end": null,
            "seating_plan": null,
            "seat_category_mapping": {},
            "location": null,
            "geo_lat": null,
            "geo_lon": null,
            "item_price_overrides": [
              {
                "item": 2,
                "price": "12.00"
              }
            ],
            "variation_price_overrides": [],
            "meta_data": {}
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :query active: If set to ``true``/``false``, only events with a matching value of ``active`` are returned.
   :query is_future: If set to ``true`` (``false``), only events that happen currently or in the future are (not) returned.
   :query is_past: If set to ``true`` (``false``), only events that are over are (not) returned.
   :query ends_after: If set to a date and time, only events that happen during of after the given time are returned.
   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of the main event
   :query array attr[meta_data_key]: By providing the key and value of a meta data attribute, the list of sub-events
        will only contain the sub-events matching the set criteria. Providing ``?attr[Format]=Seminar`` would return
        only those sub-events having set their ``Format`` meta data to ``Seminar``, ``?attr[Format]=`` only those, that
        have no value set.
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/subevents/

   Creates a new subevent.

   Permission required: "Can create events"

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/subevents/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "name": {"en": "First Sample Conference"},
        "active": false,
        "is_public": true,
        "date_from": "2017-12-27T10:00:00Z",
        "date_to": null,
        "date_admission": null,
        "presale_start": null,
        "presale_end": null,
        "location": null,
        "geo_lat": null,
        "geo_lon": null,
        "seating_plan": null,
        "seat_category_mapping": {},
        "item_price_overrides": [
          {
            "item": 2,
            "price": "12.00"
          }
        ],
        "variation_price_overrides": [],
        "meta_data": {}
      }


   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "name": {"en": "First Sample Conference"},
        "active": false,
        "is_public": true,
        "date_from": "2017-12-27T10:00:00Z",
        "date_to": null,
        "date_admission": null,
        "presale_start": null,
        "presale_end": null,
        "location": null,
        "geo_lat": null,
        "geo_lon": null,
        "seating_plan": null,
        "seat_category_mapping": {},
        "item_price_overrides": [
          {
            "item": 2,
            "price": "12.00"
          }
        ],
        "variation_price_overrides": [],
        "meta_data": {}
      }


   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of the main event
   :statuscode 201: no error
   :statuscode 400: The sub-event could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to create this resource.


.. http:get:: /api/v1/organizers/(organizer)/events/(event)/subevents/(id)/

   Returns information on one sub-event, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/subevents/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "name": {"en": "First Sample Conference"},
        "event": "sampleconf",
        "active": false,
        "is_public": true,
        "date_from": "2017-12-27T10:00:00Z",
        "date_to": null,
        "date_admission": null,
        "presale_start": null,
        "presale_end": null,
        "location": null,
        "geo_lat": null,
        "geo_lon": null,
        "seating_plan": null,
        "seat_category_mapping": {},
        "item_price_overrides": [
          {
            "item": 2,
            "price": "12.00"
          }
        ],
        "variation_price_overrides": [],
        "meta_data": {}
      }

   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of the main event
   :param id: The ``id`` field of the sub-event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view it.

.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/subevents/(id)/

   Updates a sub-event, identified by its ID. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to
   provide all fields of the resource, other fields will be reset to default. With ``PATCH``, you only need to provide
   the fields that you want to change.

   Permission required: "Can change event settings"

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/subevents/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "name": {"en": "New Subevent Name"},
        "item_price_overrides": [
          {
            "item": 2,
            "price": "23.42"
          }
        ],
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "name": {"en": "New Subevent Name"},
        "event": "sampleconf",
        "active": false,
        "is_public": true,
        "date_from": "2017-12-27T10:00:00Z",
        "date_to": null,
        "date_admission": null,
        "presale_start": null,
        "presale_end": null,
        "location": null,
        "geo_lat": null,
        "geo_lon": null,
        "seating_plan": null,
        "seat_category_mapping": {},
        "item_price_overrides": [
          {
            "item": 2,
            "price": "23.42"
          }
        ],
        "variation_price_overrides": [],
        "meta_data": {}
      }

   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of the main event
   :param id: The ``id`` field of the sub-event to update
   :statuscode 200: no error
   :statuscode 400: The sub-event could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/sub-event does not exist **or** you have no permission to update this resource.

.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/subevents/(id)/

   Delete a sub-event. Note that events with orders cannot be deleted to ensure data integrity.

   Permission required: "Can change event settings"

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/subevents/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of the main event
   :param id: The ``id`` field of the sub-event to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/sub-event does not exist **or** you have no permission to delete this resource.


.. http:get:: /api/v1/organizers/(organizer)/subevents/

   Returns a list of all sub-events of any event series you have access to within an organizer account.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/subevents/ HTTP/1.1
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
            "name": {"en": "First Sample Conference"},
            "event": "sampleconf",
            "active": false,
            "is_public": true,
            "date_from": "2017-12-27T10:00:00Z",
            "date_to": null,
            "date_admission": null,
            "presale_start": null,
            "presale_end": null,
            "location": null,
            "geo_lat": null,
            "geo_lon": null,
            "seating_plan": null,
            "seat_category_mapping": {},
            "item_price_overrides": [
              {
                "item": 2,
                "price": "12.00"
              }
            ],
            "variation_price_overrides": [],
            "meta_data": {}
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :query active: If set to ``true``/``false``, only events with a matching value of ``active`` are returned.
   :query event__live: If set to ``true``/``false``, only events with a matching value of ``live`` on the parent event are returned.
   :query is_future: If set to ``true`` (``false``), only events that happen currently or in the future are (not) returned.
   :query is_past: If set to ``true`` (``false``), only events that are over are (not) returned.
   :query ends_after: If set to a date and time, only events that happen during of after the given time are returned.
   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.
