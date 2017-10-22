Events
======

Resource description
--------------------

The event resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
name                                  multi-lingual string       The event's full name
slug                                  string                     A short form of the name, used e.g. in URLs.
live                                  boolean                    If ``true``, the event ticket shop is publicly
                                                                 available.
currency                              string                     The currency this event is handled in.
date_from                             datetime                   The event's start date
date_to                               datetime                   The event's end date (or ``null``)
date_admission                        datetime                   The event's admission date (or ``null``)
is_public                             boolean                    If ``true``, the event shows up in places like the
                                                                 organizer's public list of events
presale_start                         datetime                   The date at which the ticket shop opens (or ``null``)
presale_end                           datetime                   The date at which the ticket shop closes (or ``null``)
location                              multi-lingual string       The event location (or ``null``)
has_subevents                         boolean                    ``True`` if the event series feature is active for this
                                                                 event
meta_data                             dict                       Values set for organizer-specific meta data parameters.
===================================== ========================== =======================================================

.. versionchanged:: 1.7

   The ``meta_data`` field has been added.

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/

   Returns a list of all events within a given organizer the authenticated user/token has access to.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/ HTTP/1.1
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
            "name": {"en": "Sample Conference"},
            "slug": "sampleconf",
            "live": false,
            "currency": "EUR",
            "date_from": "2017-12-27T10:00:00Z",
            "date_to": null,
            "date_admission": null,
            "is_public": null,
            "presale_start": null,
            "presale_end": null,
            "location": null,
            "has_subevents": false,
            "meta_data": {}
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of a valid organizer
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/

   Returns information on one event, identified by its slug.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "name": {"en": "Sample Conference"},
        "slug": "sampleconf",
        "live": false,
        "currency": "EUR",
        "date_from": "2017-12-27T10:00:00Z",
        "date_to": null,
        "date_admission": null,
        "is_public": false,
        "presale_start": null,
        "presale_end": null,
        "location": null,
        "has_subevents": false,
        "meta_data": {}
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view it.
