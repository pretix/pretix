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
active                                boolean                    If ``true``, the sub-event ticket shop is publicly
                                                                 available.
date_from                             datetime                   The sub-event's start date
date_to                               datetime                   The sub-event's end date (or ``null``)
date_admission                        datetime                   The sub-event's admission date (or ``null``)
presale_start                         datetime                   The sub-date at which the ticket shop opens (or ``null``)
presale_end                           datetime                   The sub-date at which the ticket shop closes (or ``null``)
location                              multi-lingual string       The sub-event location (or ``null``)
item_price_overrides                  list of objects            List of items for which this sub-event overrides the
                                                                 default price
├ item                                integer                    The internal item ID
└ price                               money (string)             The price or ``null`` for the default price
variation_price_overrides             list of objects            List of variations for which this sub-event overrides
                                                                 the default price
├ variation                           integer                    The internal variation ID
└ price                               money (string)             The price or ``null`` for the default price
meta_data                             dict                       Values set for organizer-specific meta data parameters.
===================================== ========================== =======================================================

.. versionchanged:: 1.7

   The ``meta_data`` field has been added.


Endpoints
---------

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
            "active": false,
            "date_from": "2017-12-27T10:00:00Z",
            "date_to": null,
            "date_admission": null,
            "presale_start": null,
            "presale_end": null,
            "location": null,
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
   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.

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
        "active": false,
        "date_from": "2017-12-27T10:00:00Z",
        "date_to": null,
        "date_admission": null,
        "presale_start": null,
        "presale_end": null,
        "location": null,
        "item_price_overrides": [
          {
            "item": 2,
            "price": "12.00"
          }
        ],
        "variation_price_overrides": [],
        "meta_data": {}
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``slug`` field of the sub-event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view it.
