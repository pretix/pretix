.. spelling:word-list::

   geo
   lat
   lon

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
geo_lat                               float                      Latitude of the location (or ``null``)
geo_lon                               float                      Longitude of the location (or ``null``)
has_subevents                         boolean                    ``true`` if the event series feature is active for this
                                                                 event. Cannot change after event is created.
meta_data                             object                     Values set for organizer-specific meta data parameters.
                                                                 The allowed keys need to be set up as meta properties
                                                                 in the organizer configuration.
plugins                               list                       A list of package names of the enabled plugins for this
                                                                 event.
seating_plan                          integer                    If reserved seating is in use, the ID of a seating
                                                                 plan. Otherwise ``null``.
seat_category_mapping                 object                     An object mapping categories of the seating plan
                                                                 (strings) to items in the event (integers or ``null``).
timezone                              string                     Event timezone name
item_meta_properties                  object                     Item-specific meta data parameters and default values.
valid_keys                            object                     Cryptographic keys for non-default signature schemes.
                                                                 For performance reason, value is omitted in lists and
                                                                 only contained in detail views. Value can be cached.
all_sales_channels                    boolean                    If ``true`` (default), the event is available on all sales channels.
limit_sales_channels                  list of strings            List of sales channel identifiers the event is available on
                                                                 if ``all_sales_channels`` is ``false``.
sales_channels                        list of strings            **DEPRECATED.** Legacy interface, use ``all_sales_channels``
                                                                 and ``limit_sales_channels`` instead.
public_url                            string                     The public, customer-facing URL of the event (read-only).
===================================== ========================== =======================================================


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
            "geo_lat": null,
            "geo_lon": null,
            "has_subevents": false,
            "meta_data": {},
            "seating_plan": null,
            "seat_category_mapping": {},
            "timezone": "Europe/Berlin",
            "item_meta_properties": {},
            "plugins": [
              "pretix.plugins.banktransfer",
              "pretix.plugins.stripe",
              "pretix.plugins.paypal",
              "pretix.plugins.ticketoutputpdf"
            ],
            "all_sales_channels": false,
            "limit_sales_channels": [
              "web",
              "pretixpos",
              "resellers"
            ],
            "sales_channels": [],
            "public_url": "https://pretix.eu/bigevents/sampleconf/"
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :query is_public: If set to ``true``/``false``, only events with a matching value of ``is_public`` are returned.
   :query live: If set to ``true``/``false``, only events with a matching value of ``live`` are returned.
   :query testmode: If set to ``true``/``false``, only events with a matching value of ``testmode`` are returned.
   :query has_subevents: If set to ``true``/``false``, only events with a matching value of ``has_subevents`` are returned.
   :query is_future: If set to ``true`` (``false``), only events that happen currently or in the future are (not) returned. Event series are never (always) returned.
   :query is_past: If set to ``true`` (``false``), only events that are over are (not) returned. Event series are never (always) returned.
   :query date_from_after: If set to a date and time, only events that start at or after the given time are returned.
   :query date_from_before: If set to a date and time, only events that start at or before the given time are returned.
   :query date_to_after: If set to a date and time, only events that have an end date and end at or after the given time are returned.
   :query date_to_before: If set to a date and time, only events that have an end date and end at or before the given time are returned.
   :query ends_after: If set to a date and time, only events that happen during of after the given time are returned. Event series are never returned.
   :query string ordering: Manually set the ordering of results. Valid fields to be used are ``date_from`` and
                           ``slug``. Keep in mind that ``date_from`` of event series does not really tell you anything.
                           Default: ``slug``.
   :query array attr[meta_data_key]: By providing the key and value of a meta data attribute, the list of events will
        only contain the events matching the set criteria. Providing ``?attr[Format]=Seminar`` would return only those
        events having set their ``Format`` meta data to ``Seminar``, ``?attr[Format]=`` only those, that have no value
        set. Please note that this filter will respect default values set on organizer level.
   :query sales_channel: If set to a sales channel identifier, only events allowed to be sold on the specified sales channel are returned.
   :query with_availability_for: If set to a sales channel identifier, the response will contain a special ``best_availability_state``
                                 attribute with values of 100 for "tickets available", values less than 100 for "tickets sold out or reserved",
                                 and ``null`` for "status unknown". These values might be served from a cache. This parameter can make the response
                                 slow.
   :query search: Only return events matching a given search query.
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
        "geo_lat": null,
        "geo_lon": null,
        "has_subevents": false,
        "seating_plan": null,
        "seat_category_mapping": {},
        "meta_data": {},
        "timezone": "Europe/Berlin",
        "item_meta_properties": {},
        "plugins": [
          "pretix.plugins.banktransfer",
          "pretix.plugins.stripe",
          "pretix.plugins.paypal",
          "pretix.plugins.ticketoutputpdf"
        ],
        "valid_keys": {
          "pretix_sig1": [
            "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUNvd0JRWURLMlZ3QXlFQTdBRDcvdkZBMzNFc1k0ejJQSHI3aVpQc1o4bjVkaDBhalA4Z3l6Tm1tSXM9Ci0tLS0tRU5EIFBVQkxJQyBLRVktLS0tLQo="
          ]
        },
        "all_sales_channels": true,
        "limit_sales_channels": [],
        "sales_channels": [
          "web",
          "pretixpos",
          "resellers"
        ],
        "public_url": "https://pretix.eu/bigevents/sampleconf/"
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
        "seating_plan": null,
        "seat_category_mapping": {},
        "location": null,
        "geo_lat": null,
        "geo_lon": null,
        "has_subevents": false,
        "meta_data": {},
        "timezone": "Europe/Berlin",
        "item_meta_properties": {},
        "plugins": [
          "pretix.plugins.stripe",
          "pretix.plugins.paypal"
        ],
        "all_sales_channels": true,
        "limit_sales_channels": []
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
        "geo_lat": null,
        "geo_lon": null,
        "seating_plan": null,
        "seat_category_mapping": {},
        "has_subevents": false,
        "meta_data": {},
        "timezone": "Europe/Berlin",
        "item_meta_properties": {},
        "plugins": [
          "pretix.plugins.stripe",
          "pretix.plugins.paypal"
        ],
        "all_sales_channels": true,
        "limit_sales_channels": [],
        "sales_channels": [
          "web",
          "pretixpos",
          "resellers"
        ],
        "public_url": "https://pretix.eu/bigevents/sampleconf/"
      }

   :param organizer: The ``slug`` field of the organizer of the event to create.
   :query clone_from: Set to ``event_slug`` to clone data (settings, products, …) from an event with this slug in the
                      same organizer or to ``organizer_slug/event_slug`` to clone from an event within a different
                      organizer.
   :statuscode 201: no error
   :statuscode 400: The event could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to create this resource.


.. http:post:: /api/v1/organizers/(organizer)/events/(event)/clone/

   Creates a new event with properties as set in the request body. The properties that are copied are: ``is_public``,
   ``testmode``, ``has_subevents``, settings, plugin settings, items, variations, add-ons, quotas, categories, tax rules, questions.

   If the ``plugins``, ``has_subevents``, ``meta_data`` and/or ``is_public`` fields are present in the post body this will
   determine their  value. Otherwise their value will be copied from the existing event.

   Please note that you can only copy from events under the same organizer this way. Use the ``clone_from`` parameter
   when creating a new event for this instead.

   Permission required: "Can create events"

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/clone/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
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
        "geo_lat": null,
        "geo_lon": null,
        "seating_plan": null,
        "seat_category_mapping": {},
        "has_subevents": false,
        "meta_data": {},
        "timezone": "Europe/Berlin",
        "item_meta_properties": {},
        "plugins": [
          "pretix.plugins.stripe",
          "pretix.plugins.paypal"
        ],
        "all_sales_channels": true,
        "limit_sales_channels": []
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
        "geo_lat": null,
        "geo_lon": null,
        "has_subevents": false,
        "seating_plan": null,
        "seat_category_mapping": {},
        "meta_data": {},
        "timezone": "Europe/Berlin",
        "item_meta_properties": {},
        "plugins": [
          "pretix.plugins.stripe",
          "pretix.plugins.paypal"
        ],
        "all_sales_channels": true,
        "limit_sales_channels": [],
        "sales_channels": [
          "web",
          "pretixpos",
          "resellers"
        ],
        "public_url": "https://pretix.eu/bigevents/sampleconf/"
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
      Content-Type: application/json

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
        "geo_lat": null,
        "geo_lon": null,
        "has_subevents": false,
        "seating_plan": null,
        "seat_category_mapping": {},
        "meta_data": {},
        "timezone": "Europe/Berlin",
        "item_meta_properties": {},
        "plugins": [
          "pretix.plugins.banktransfer",
          "pretix.plugins.stripe",
          "pretix.plugins.paypal",
          "pretix.plugins.pretixdroid"
        ],
        "all_sales_channels": true,
        "limit_sales_channels": [],
        "sales_channels": [
          "web",
          "pretixpos",
          "resellers"
        ],
        "public_url": "https://pretix.eu/bigevents/sampleconf/"
      }

   :param organizer: The ``slug`` field of the organizer of the event to update
   :param event: The ``slug`` field of the event to update
   :statuscode 200: no error
   :statuscode 400: The event could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this resource.


.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/

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

Event settings
--------------

pretix events have lots and lots of parameters of different types that are stored in a key-value store on our system.
Since many of these settings depend on each other in complex ways, we can not give direct access to all of these
settings through the API. However, we do expose many of the simple and useful flags through the API.

Please note that the available settings flags change between pretix versions and also between events, depending on the
installed plugins, and we do not give a guarantee on backwards-compatibility like with other parts of the API.
Therefore, we're also not including a list of the options here, but instead recommend to look at the endpoint output
to see available options. The ``explain=true`` flag enables a verbose mode that provides you with human-readable
information about the properties.

Note that some settings are read-only, e.g. because they can be read on event level but currently only be changed on
organizer level.

.. note:: Please note that this is not a complete representation of all event settings. You will find more settings
          in the web interface.

.. warning:: This API is intended for advanced users. Even though we take care to validate your input, you will be
             able to break your event using this API by creating situations of conflicting settings. Please take care.

.. note:: When authenticating with :ref:`rest-deviceauth`, only a limited subset of settings is available.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/settings/

   Get current values of event settings.

   Permission required: "Can change event settings" (Exception: with device auth, *some* settings can always be *read*.)

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/settings/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example standard response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "imprint_url": "https://pretix.eu",
        …
      }

   **Example verbose response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "imprint_url":
          {
            "value": "https://pretix.eu",
            "label": "Imprint URL",
            "readonly": false,
            "help_text": "This should point e.g. to a part of your website that has your contact details and legal information."
          }
        },
        …
      }

   :param organizer: The ``slug`` field of the organizer of the event to access
   :param event: The ``slug`` field of the event to access
   :query explain: Set to ``true`` to enable verbose response mode
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/settings/

   Updates event settings. Note that ``PUT`` is not allowed here, only ``PATCH``.

    .. warning::

       Settings can be stored at different levels in pretix. If a value is not set on event level, a default setting
       from a higher level (organizer, global) will be returned. If you explicitly set a setting on event level, it
       will no longer be inherited from the higher levels. Therefore, we recommend you to send only settings that you
       explicitly want to set on event level. To unset a settings, pass ``null``.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/settings/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "imprint_url": "https://example.org/imprint/"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "imprint_url": "https://example.org/imprint/",
        …
      }

   :param organizer: The ``slug`` field of the organizer of the event to update
   :param event: The ``slug`` field of the event to update
   :statuscode 200: no error
   :statuscode 400: The event could not be updated due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this resource.
