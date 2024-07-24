Scheduled email rules
=====================

This feature requires the bundled ``pretix.plugins.sendmail`` plugin to be active for the event in order to work properly.

Resource description
--------------------

Scheduled email rules that specify emails that the system will send automatically at a specific point in time, e.g.
the day of the event.

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the rule
enabled                               boolean                    If ``false``, the rule is ignored
subject                               multi-lingual string       The subject of the email
template                              multi-lingual string       The body of the email
all_products                          boolean                    If ``true``, the email is sent to buyers of all products
limit_products                        list of integers           List of product IDs, if ``all_products`` is not set
[**DEPRECATED**] include_pending      boolean                    If ``true``, the email is sent to pending orders. If ``false``,
                                                                 only paid orders are considered.
restrict_to_status                    list                       List of order states to restrict recipients to. Valid
                                                                 entries are ``p`` for paid, ``e`` for expired, ``c`` for canceled,
                                                                 ``n__pending_approval`` for pending approval,
                                                                 ``n__not_pending_approval_and_not_valid_if_pending`` for payment
                                                                 pending, ``n__valid_if_pending`` for payment pending but already confirmed,
                                                                 and ``n__pending_overdue`` for pending with payment overdue.
                                                                 The default is ``["p", "n__valid_if_pending"]``.
checked_in_status                     string                     Check-in status to restrict recipients to. Valid strings are:
                                                                 ``null`` for no filtering (default), ``checked_in`` for
                                                                 limiting to attendees that are or have been checked in, and
                                                                 ``no_checkin`` for limiting to attendees who have not checked in.
date_is_absolute                      boolean                    If ``true``, the email is set at a specific point in time.
send_date                             datetime                   If ``date_is_absolute`` is set: Date and time to send the email.
send_offset_days                      integer                    If ``date_is_absolute`` is not set, this is the number of days
                                                                 before/after the email is sent.
send_offset_time                      time                       If ``date_is_absolute`` is not set, this is the time of day the
                                                                 email is sent on the day specified by ``send_offset_days``.
offset_to_event_end                   boolean                    If ``true``, ``send_offset_days`` is relative to the event end
                                                                 date. Otherwise it is relative to the event start date.
offset_is_after                       boolean                    If ``true``, ``send_offset_days`` is the number of days **after**
                                                                 the event start or end date. Otherwise it is the number of days
                                                                 **before**.
send_to                               string                     Can be ``"orders"`` if the email should be sent to customers
                                                                 (one email per order),
                                                                 ``"attendees"`` if the email should be sent to every attendee,
                                                                 or ``"both"``.
                                                                 date. Otherwise it is relative to the event start date.
===================================== ========================== =======================================================

.. versionchanged:: 2023.7

    The ``include_pending`` field has been  deprecated.
    The ``restrict_to_status`` field has been added.

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/sendmail_rules/

   Returns a list of all rules configured for an event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/sendmail_rules/ HTTP/1.1
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
            "enabled": true,
            "subject": {"en": "See you tomorrow!"},
            "template": {"en": "Don't forget your tickets, download them at {url}"},
            "all_products": true,
            "limit_products": [],
            "restrict_to_status": [
                "p",
                "n__not_pending_approval_and_not_valid_if_pending",
                "n__valid_if_pending"
            ],
            "checked_in_status": null,
            "send_date": null,
            "send_offset_days": 1,
            "send_offset_time": "18:00",
            "date_is_absolute": false,
            "offset_to_event_end": false,
            "offset_is_after": false,
            "send_to": "orders"
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/sendmail_rules/(id)/

   Returns information on one rule, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/sendmail_rules/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "enabled": true,
        "subject": {"en": "See you tomorrow!"},
        "template": {"en": "Don't forget your tickets, download them at {url}"},
        "all_products": true,
        "limit_products": [],
        "restrict_to_status": [
            "p",
            "n__not_pending_approval_and_not_valid_if_pending",
            "n__valid_if_pending"
        ],
        "checked_in_status": null,
        "send_date": null,
        "send_offset_days": 1,
        "send_offset_time": "18:00",
        "date_is_absolute": false,
        "offset_to_event_end": false,
        "offset_is_after": false,
        "send_to": "orders"
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the rule to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event/rule does not exist **or** you have no permission to view it.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/sendmail_rules/

   Create a new rule.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/sendmail_rules/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 166

      {
        "enabled": true,
        "subject": {"en": "See you tomorrow!"},
        "template": {"en": "Don't forget your tickets, download them at {url}"},
        "all_products": true,
        "limit_products": [],
        "restrict_to_status": [
            "p",
            "n__not_pending_approval_and_not_valid_if_pending",
            "n__valid_if_pending"
        ],
        "checked_in_status": "checked_in",
        "send_date": null,
        "send_offset_days": 1,
        "send_offset_time": "18:00",
        "date_is_absolute": false,
        "offset_to_event_end": false,
        "offset_is_after": false,
        "send_to": "orders"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "enabled": true,
        "subject": {"en": "See you tomorrow!"},
        "template": {"en": "Don't forget your tickets, download them at {url}"},
        "all_products": true,
        "limit_products": [],
        "restrict_to_status": [
            "p",
            "n__not_pending_approval_and_not_valid_if_pending",
            "n__valid_if_pending"
        ],
        "checked_in_status": "checked_in",
        "send_date": null,
        "send_offset_days": 1,
        "send_offset_time": "18:00",
        "date_is_absolute": false,
        "offset_to_event_end": false,
        "offset_is_after": false,
        "send_to": "orders"
      }

   :param organizer: The ``slug`` field of the organizer to create a rule for
   :param event: The ``slug`` field of the event to create a rule for
   :statuscode 201: no error
   :statuscode 400: The rule could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create rules.


.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/sendmail_rules/(id)/

   Update a rule. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/sendmail_rules/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 34

      {
        "enabled": false,
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: text/javascript

      {
        "id": 1,
        "enabled": false,
        "subject": {"en": "See you tomorrow!"},
        "template": {"en": "Don't forget your tickets, download them at {url}"},
        "all_products": true,
        "limit_products": [],
        "restrict_to_status": [
            "p",
            "n__not_pending_approval_and_not_valid_if_pending",
            "n__valid_if_pending"
        ],
        "checked_in_status": "checked_in",
        "send_date": null,
        "send_offset_days": 1,
        "send_offset_time": "18:00",
        "date_is_absolute": false,
        "offset_to_event_end": false,
        "offset_is_after": false,
        "send_to": "orders"
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the rule to modify
   :statuscode 200: no error
   :statuscode 400: The rule could not be modified due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event/rule does not exist **or** you have no permission to change it.


.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/sendmail_rules/(id)/

   Delete a rule.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/sendmail_rules/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the rule to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event/rule does not exist **or** you have no permission to change it **or** this rule cannot be deleted since it is currently in use.
