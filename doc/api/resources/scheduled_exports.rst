.. spelling:word-list:: checkin

Scheduled data exports
======================

pretix and it's plugins include a number of data exporters that allow you to bulk download various data from pretix in
different formats. You should read :ref:`rest-exporters` first to get an understanding of the basic mechanism.

Exports can be scheduled to be sent at specific times automatically, both on organizer level and event level.

Scheduled export resource
-------------------------

The scheduled export contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the schedule
owner                                 string                     Email address of the user who created this schedule (read-only).
                                                                 This address will always receive the export and the export
                                                                 will only contain data that this user has permission
                                                                 to access at the time of the export. **We consider this
                                                                 field experimental, it's behaviour might change in the future.
                                                                 Note that the email address of a user can change at any time.**
export_identifier                     string                     Identifier of the export to run, see :ref:`rest-exporters`
export_form_data                      object                     Input data for the export, format depends on the export,
                                                                 see :ref:`rest-exporters` for more details.
locale                                string                     Language to run the export in
mail_additional_recipients            string                     Email addresses to receive the export, comma-separated (or empty string)
mail_additional_recipients_cc         string                     Email addresses to receive the export in copy, comma-separated (or empty string)
mail_additional_recipients_bcc        string                     Email addresses to receive the exportin blind copy, comma-separated (or empty string)
mail_subject                          string                     Subject to use for the email (currently no variables supported)
mail_template                         string                     Text to use for the email (currently no variables supported)
schedule_rrule                        string                     Recurrence specification to determine the **days** this
                                                                 schedule runs on in ``RRULE`` syntax following `RFC 5545`_
                                                                 with some restrictions. Only one rule is allowed, only
                                                                 one occurrence per day is allowed, and some features
                                                                 are not supported (``BYMONTHDAY``, ``BYYEARDAY``,
                                                                 ``BYEASTER``, ``BYWEEKNO``).
schedule_rrule_time                   time                       Time of day to run this on on the specified days.
                                                                 Will be interpreted as local time of the event for event-level
                                                                 exports. For organizer-level exports, the timezone is given
                                                                 in the field ``timezone``. The export will never run **before**
                                                                 this time but it **may** run **later**.
timezone                              string                     Time zone to interpret the schedule in (only for organizer-level exports)
schedule_next_run                     datetime                   Next planned execution (read-only, computed by server)
error_counter                         integer                    Number of consecutive times this export failed (read-only).
                                                                 After a number of failures (currently 5), the schedule no
                                                                 longer is executed. Changing parameters resets the value.
===================================== ========================== =======================================================

Special notes on permissions
----------------------------

Permission handling for scheduled exports is more complex than for most other objects. The reason for this is that
there are two levels of access control involved here: First, you need permission to access or change the configuration
of the scheduled exports in the moment you are doing it. Second, you **continuously** need permission to access the
**data** that is exported as part of the schedule. For this reason, scheduled exports always need one user account
to be their **owner**.

Therefore, scheduled exports **must** be created by an API client using :ref:`OAuth authentication <rest-oauth>`.
It is impossible to create a scheduled export using token authentication. After the export is created, it can also be
modified using token authentication.

A user or token with the "can change settings" permission for a given organizer or event can see and change
**all** scheduled exports created for the respective organizer or event, regardless of who created them.
A user without this permission can only see **their own** scheduled exports.
A token without this permission can not see scheduled exports as all.



Endpoints for event exports
---------------------------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/scheduled_exports/

   Returns a list of all scheduled exports the client has access to.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/scheduled_exports/ HTTP/1.1
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
            "owner": "john@example.com",
            "export_identifier": "orderlist",
            "export_form_data": {"_format": "xlsx", "date_range": "week_previous"},
            "locale": "en",
            "mail_additional_recipients": "mary@example.org",
            "mail_additional_recipients_cc": "",
            "mail_additional_recipients_bcc": "",
            "mail_subject": "Order list",
            "mail_template": "Here is last week's order list\n\nCheers\nJohn",
            "schedule_rrule": "DTSTART:20230118T000000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH",
            "schedule_rrule_time": "04:00:00",
            "schedule_next_run": "2023-10-26T02:00:00Z",
            "error_counter": 0
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query string ordering: Manually set the ordering of results. Valid fields to be used are ``id``, ``export_identifier``, and ``schedule_next_run``.
                           Default: ``id``
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/scheduled_exports/(id)/

   Returns information on one scheduled export, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/scheduled_exports/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "owner": "john@example.com",
        "export_identifier": "orderlist",
        "export_form_data": {"_format": "xlsx", "date_range": "week_previous"},
        "locale": "en",
        "mail_additional_recipients": "mary@example.org",
        "mail_additional_recipients_cc": "",
        "mail_additional_recipients_bcc": "",
        "mail_subject": "Order list",
        "mail_template": "Here is last week's order list\n\nCheers\nJohn",
        "schedule_rrule": "DTSTART:20230118T000000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH",
        "schedule_rrule_time": "04:00:00",
        "schedule_next_run": "2023-10-26T02:00:00Z",
        "error_counter": 0
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the scheduled export to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/scheduled_exports/

   Schedule a new export.

   .. note:: See above for special notes on permissions.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/scheduled_exports/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "export_identifier": "orderlist",
        "export_form_data": {"_format": "xlsx", "date_range": "week_previous"},
        "locale": "en",
        "mail_additional_recipients": "mary@example.org",
        "mail_additional_recipients_cc": "",
        "mail_additional_recipients_bcc": "",
        "mail_subject": "Order list",
        "mail_template": "Here is last week's order list\n\nCheers\nJohn",
        "schedule_rrule": "DTSTART:20230118T000000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH",
        "schedule_rrule_time": "04:00:00"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json


      {
        "id": 1,
        "owner": "john@example.com",
        "export_identifier": "orderlist",
        "export_form_data": {"_format": "xlsx", "date_range": "week_previous"},
        "locale": "en",
        "mail_additional_recipients": "mary@example.org",
        "mail_additional_recipients_cc": "",
        "mail_additional_recipients_bcc": "",
        "mail_subject": "Order list",
        "mail_template": "Here is last week's order list\n\nCheers\nJohn",
        "schedule_rrule": "DTSTART:20230118T000000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH",
        "schedule_rrule_time": "04:00:00",
        "schedule_next_run": "2023-10-26T02:00:00Z",
        "error_counter": 0
      }

   :param organizer: The ``slug`` field of the organizer of the event to create an item for
   :param event: The ``slug`` field of the event to create an item for
   :statuscode 201: no error
   :statuscode 400: The item could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/scheduled_exports/(id)/

   Update a scheduled export. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/scheduled_exports/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "export_form_data": {"_format": "xlsx", "date_range": "week_this"},
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "owner": "john@example.com",
        "export_identifier": "orderlist",
        "export_form_data": {"_format": "xlsx", "date_range": "week_this"},
        "locale": "en",
        "mail_additional_recipients": "mary@example.org",
        "mail_additional_recipients_cc": "",
        "mail_additional_recipients_bcc": "",
        "mail_subject": "Order list",
        "mail_template": "Here is last week's order list\n\nCheers\nJohn",
        "schedule_rrule": "DTSTART:20230118T000000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH",
        "schedule_rrule_time": "04:00:00",
        "schedule_next_run": "2023-10-26T02:00:00Z",
        "error_counter": 0
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the export to modify
   :statuscode 200: no error
   :statuscode 400: The export could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to change this resource.

.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/scheduled_exports/(id)/

   Delete a scheduled export.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/scheduled_exports/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the export to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to delete this resource.

Endpoints for organizer exports
-------------------------------

.. http:get:: /api/v1/organizers/(organizer)/scheduled_exports/

   Returns a list of all scheduled exports the client has access to.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/scheduled_exports/ HTTP/1.1
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
            "owner": "john@example.com",
            "export_identifier": "orderlist",
            "export_form_data": {"_format": "xlsx", "date_range": "week_previous"},
            "locale": "en",
            "mail_additional_recipients": "mary@example.org",
            "mail_additional_recipients_cc": "",
            "mail_additional_recipients_bcc": "",
            "mail_subject": "Order list",
            "mail_template": "Here is last week's order list\n\nCheers\nJohn",
            "schedule_rrule": "DTSTART:20230118T000000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH",
            "schedule_rrule_time": "04:00:00",
            "schedule_next_run": "2023-10-26T02:00:00Z",
            "timezone": "Europe/Berlin",
            "error_counter": 0
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query string ordering: Manually set the ordering of results. Valid fields to be used are ``id``, ``export_identifier``, and ``schedule_next_run``.
                           Default: ``id``
   :param organizer: The ``slug`` field of the organizer to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/scheduled_exports/(id)/

   Returns information on one scheduled export, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/scheduled_exports/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "owner": "john@example.com",
        "export_identifier": "orderlist",
        "export_form_data": {"_format": "xlsx", "date_range": "week_previous"},
        "locale": "en",
        "mail_additional_recipients": "mary@example.org",
        "mail_additional_recipients_cc": "",
        "mail_additional_recipients_bcc": "",
        "mail_subject": "Order list",
        "mail_template": "Here is last week's order list\n\nCheers\nJohn",
        "schedule_rrule": "DTSTART:20230118T000000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH",
        "schedule_rrule_time": "04:00:00",
        "schedule_next_run": "2023-10-26T02:00:00Z",
        "timezone": "Europe/Berlin",
        "error_counter": 0
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param id: The ``id`` field of the scheduled export to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/scheduled_exports/

   Schedule a new export.

   .. note:: See above for special notes on permissions.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/scheduled_exports/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "export_identifier": "orderlist",
        "export_form_data": {"_format": "xlsx", "date_range": "week_previous"},
        "locale": "en",
        "mail_additional_recipients": "mary@example.org",
        "mail_additional_recipients_cc": "",
        "mail_additional_recipients_bcc": "",
        "mail_subject": "Order list",
        "mail_template": "Here is last week's order list\n\nCheers\nJohn",
        "schedule_rrule": "DTSTART:20230118T000000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH",
        "schedule_rrule_time": "04:00:00",
        "timezone": "Europe/Berlin"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json


      {
        "id": 1,
        "owner": "john@example.com",
        "export_identifier": "orderlist",
        "export_form_data": {"_format": "xlsx", "date_range": "week_previous"},
        "locale": "en",
        "mail_additional_recipients": "mary@example.org",
        "mail_additional_recipients_cc": "",
        "mail_additional_recipients_bcc": "",
        "mail_subject": "Order list",
        "mail_template": "Here is last week's order list\n\nCheers\nJohn",
        "schedule_rrule": "DTSTART:20230118T000000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH",
        "schedule_rrule_time": "04:00:00",
        "schedule_next_run": "2023-10-26T02:00:00Z",
        "timezone": "Europe/Berlin",
        "error_counter": 0
      }

   :param organizer: The ``slug`` field of the organizer of the event to create an item for
   :statuscode 201: no error
   :statuscode 400: The item could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/scheduled_exports/(id)/

   Update a scheduled export. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/scheduled_exports/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "export_form_data": {"_format": "xlsx", "date_range": "week_this"},
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "owner": "john@example.com",
        "export_identifier": "orderlist",
        "export_form_data": {"_format": "xlsx", "date_range": "week_this"},
        "locale": "en",
        "mail_additional_recipients": "mary@example.org",
        "mail_additional_recipients_cc": "",
        "mail_additional_recipients_bcc": "",
        "mail_subject": "Order list",
        "mail_template": "Here is last week's order list\n\nCheers\nJohn",
        "schedule_rrule": "DTSTART:20230118T000000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH",
        "schedule_rrule_time": "04:00:00",
        "schedule_next_run": "2023-10-26T02:00:00Z",
        "timezone": "Europe/Berlin",
        "error_counter": 0
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param id: The ``id`` field of the export to modify
   :statuscode 200: no error
   :statuscode 400: The export could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to change this resource.

.. http:delete:: /api/v1/organizers/(organizer)/scheduled_exports/(id)/

   Delete a scheduled export.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/scheduled_exports/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param id: The ``id`` field of the export to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to delete this resource.


.. _RFC 5545: https://datatracker.ietf.org/doc/html/rfc5545#section-3.8.5.3
