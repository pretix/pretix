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
testmode                              boolean                    If ``true``, the ticket shop is in test mode.
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
                                                                 event. Cannot change after event is created.
meta_data                             dict                       Values set for organizer-specific meta data parameters.
plugins                               list                       A list of package names of the enabled plugins for this
                                                                 event.
===================================== ========================== =======================================================


.. versionchanged:: 1.7

   The ``meta_data`` field has been added.

.. versionchanged:: 1.15

   The ``plugins`` field has been added.
   The operations POST, PATCH, PUT and DELETE have been added.

.. versionchanged:: 2.1

   Filters have been added to the list of events.

.. versionchanged:: 2.5

   The ``testmode`` attribute has been added.

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/

   Returns a list of all events within a given organizer the authenticated user/token has access to.

   Permission required: "Can change event settings"

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
            "testmode": false,
            "currency": "EUR",
            "date_from": "2017-12-27T10:00:00Z",
            "date_to": null,
            "date_admission": null,
            "is_public": null,
            "presale_start": null,
            "presale_end": null,
            "location": null,
            "has_subevents": false,
            "meta_data": {},
            "plugins": [
              "pretix.plugins.banktransfer"
              "pretix.plugins.stripe"
              "pretix.plugins.paypal"
              "pretix.plugins.ticketoutputpdf"
            ]
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :query is_public: If set to ``true``/``false``, only events with a matching value of ``is_public`` are returned.
   :query live: If set to ``true``/``false``, only events with a matching value of ``live`` are returned.
   :query has_subevents: If set to ``true``/``false``, only events with a matching value of ``has_subevents`` are returned.
   :query is_future: If set to ``true`` (``false``), only events that happen currently or in the future are (not) returned. Event series are never (always) returned.
   :query is_past: If set to ``true`` (``false``), only events that are over are (not) returned. Event series are never (always) returned.
   :query ends_after: If set to a date and time, only events that happen during of after the given time are returned. Event series are never returned.
   :param organizer: The ``slug`` field of a valid organizer
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/

   Returns information on one event, identified by its slug.

   Permission required: "Can change event settings"

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
        "testmode": false,
        "currency": "EUR",
        "date_from": "2017-12-27T10:00:00Z",
        "date_to": null,
        "date_admission": null,
        "is_public": false,
        "presale_start": null,
        "presale_end": null,
        "location": null,
        "has_subevents": false,
        "meta_data": {},
        "plugins": [
          "pretix.plugins.banktransfer"
          "pretix.plugins.stripe"
          "pretix.plugins.paypal"
          "pretix.plugins.ticketoutputpdf"
        ]
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view it.

.. http:post:: /api/v1/organizers/(organizer)/events/

   Creates a new event

   Please note that events cannot be created as 'live' using this endpoint. Quotas and payment must be added to the
   event before sales can go live.

   Permission required: "Can create events"

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content: application/json

      {
        "name": {"en": "Sample Conference"},
        "slug": "sampleconf",
        "live": false,
        "testmode": false,
        "currency": "EUR",
        "date_from": "2017-12-27T10:00:00Z",
        "date_to": null,
        "date_admission": null,
        "is_public": false,
        "presale_start": null,
        "presale_end": null,
        "location": null,
        "has_subevents": false,
        "meta_data": {},
        "plugins": [
          "pretix.plugins.stripe",
          "pretix.plugins.paypal"
        ]
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "name": {"en": "Sample Conference"},
        "slug": "sampleconf",
        "live": false,
        "testmode": false,
        "currency": "EUR",
        "date_from": "2017-12-27T10:00:00Z",
        "date_to": null,
        "date_admission": null,
        "is_public": false,
        "presale_start": null,
        "presale_end": null,
        "location": null,
        "has_subevents": false,
        "meta_data": {},
        "plugins": [
          "pretix.plugins.stripe",
          "pretix.plugins.paypal"
        ]
      }

   :param organizer: The ``slug`` field of the organizer of the event to create.
   :statuscode 201: no error
   :statuscode 400: The event could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to create this resource.


.. http:post:: /api/v1/organizers/(organizer)/events/(event)/clone/

   Creates a new event with properties as set in the request body. The properties that are copied are: 'is_public',
   settings, plugin settings, items, variations, add-ons, quotas, categories, tax rules, questions.

   If the 'plugins' and/or 'is_public' fields are present in the post body this will determine their value. Otherwise
   their value will be copied from the existing event.

   Please note that you can only copy from events under the same organizer.

   Permission required: "Can create events"

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/clone/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content: application/json

      {
        "name": {"en": "Sample Conference"},
        "slug": "sampleconf",
        "live": false,
        "testmode": false,
        "currency": "EUR",
        "date_from": "2017-12-27T10:00:00Z",
        "date_to": null,
        "date_admission": null,
        "is_public": false,
        "presale_start": null,
        "presale_end": null,
        "location": null,
        "has_subevents": false,
        "meta_data": {},
        "plugins": [
          "pretix.plugins.stripe",
          "pretix.plugins.paypal"
        ]
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "name": {"en": "Sample Conference"},
        "slug": "sampleconf",
        "live": false,
        "testmode": false,
        "currency": "EUR",
        "date_from": "2017-12-27T10:00:00Z",
        "date_to": null,
        "date_admission": null,
        "is_public": false,
        "presale_start": null,
        "presale_end": null,
        "location": null,
        "has_subevents": false,
        "meta_data": {},
        "plugins": [
          "pretix.plugins.stripe",
          "pretix.plugins.paypal"
        ]
      }

   :param organizer: The ``slug`` field of the organizer of the event to create.
   :param event: The ``slug`` field of the event to copy settings and items from.
   :statuscode 201: no error
   :statuscode 400: The event could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to create this resource.


.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/

   Updates an event

   Permission required: "Can change event settings"

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content: application/json

      {
        "plugins": [
          "pretix.plugins.banktransfer",
          "pretix.plugins.stripe",
          "pretix.plugins.paypal",
          "pretix.plugins.pretixdroid"
        ]
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "name": {"en": "Sample Conference"},
        "slug": "sampleconf",
        "live": false,
        "testmode": false,
        "currency": "EUR",
        "date_from": "2017-12-27T10:00:00Z",
        "date_to": null,
        "date_admission": null,
        "is_public": false,
        "presale_start": null,
        "presale_end": null,
        "location": null,
        "has_subevents": false,
        "meta_data": {},
        "plugins": [
          "pretix.plugins.banktransfer",
          "pretix.plugins.stripe",
          "pretix.plugins.paypal",
          "pretix.plugins.pretixdroid"
        ]
      }

   :param organizer: The ``slug`` field of the organizer of the event to update
   :param event: The ``slug`` field of the event to update
   :statuscode 200: no error
   :statuscode 400: The event could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this resource.


.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/items/(id)/

   Delete an event. Note that events with orders cannot be deleted to ensure data integrity.

   Permission required: "Can change event settings"

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to delete this resource.
