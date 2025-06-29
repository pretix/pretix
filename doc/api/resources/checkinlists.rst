.. spelling:word-list:: checkin

.. _rest-checkinlists:

Check-in lists
==============

Resource description
--------------------

You can create check-in lists that you can use e.g. at the entrance of your event to track who is coming and if they
actually bought a ticket.

You can create multiple check-in lists to separate multiple parts of your event, for example if you have separate
entries for multiple ticket types. Different check-in lists are completely independent: If a ticket shows up on two
lists, it is valid once on every list. This might be useful if you run a festival with festival passes that allow
access to every or multiple performances as well as tickets only valid for single performances.

The check-in list resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the check-in list
name                                  string                     The internal name of the check-in list
all_products                          boolean                    If ``true``, the check-in lists contains tickets of all products in this event. The ``limit_products`` field is ignored in this case.
limit_products                        list of integers           List of item IDs to include in this list.
subevent                              integer                    ID of the date inside an event series this list belongs to (or ``null``).
position_count                        integer                    Number of tickets that match this list (read-only).
checkin_count                         integer                    Number of check-ins performed on this list (read-only).
include_pending                       boolean                    If ``true``, the check-in list also contains tickets from orders in pending state.
allow_multiple_entries                boolean                    If ``true``, subsequent scans of a ticket on this list should not show a warning but instead be stored as an additional check-in.
allow_entry_after_exit                boolean                    If ``true``, subsequent scans of a ticket on this list are valid if the last scan of the ticket was an exit scan.
rules                                 object                     Custom check-in logic. The contents of this field are currently not considered a stable API and modifications through the API are highly discouraged.
exit_all_at                           datetime                   Automatically check out (i.e. perform an exit scan) at this point in time. After this happened, this property will automatically be set exactly one day into the future. Note that this field is considered "internal configuration" and if you pull the list with ``If-Modified-Since``, the daily change in this field will not trigger a response.
addon_match                           boolean                    If ``true``, tickets on this list can be redeemed by scanning their parent ticket if this still leads to an unambiguous match.
ignore_in_statistics                  boolean                    If ``true``, check-ins on this list will be ignored in most reporting features.
consider_tickets_used                 boolean                    If ``true`` (default), tickets checked in on this list will be considered "used" by other functionality, i.e. when checking if they can still be canceled.
===================================== ========================== =======================================================

.. versionchanged:: 2023.9

    The ``ignore_in_statistics`` and ``consider_tickets_used`` attributes have been added.

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/checkinlists/

   Returns a list of all check-in lists within a given event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/checkinlists/ HTTP/1.1
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
            "name": "Default list",
            "checkin_count": 123,
            "position_count": 456,
            "all_products": true,
            "limit_products": [],
            "include_pending": false,
            "subevent": null,
            "allow_multiple_entries": false,
            "allow_entry_after_exit": true,
            "exit_all_at": null,
            "rules": {},
            "addon_match": false
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query integer subevent: Only return check-in lists of the sub-event with the given ID
   :query integer subevent_match: Only return check-in lists that are valid for the sub-event with the given ID (i.e. also lists valid for all subevents)
   :query string ends_after: Exclude all check-in lists attached to a sub-event that is already in the past at the given time.
   :query string expand: Expand a field into a full object. Currently only ``subevent`` is supported. Can be passed multiple times.
   :query string exclude: Exclude a field from the output, e.g. ``checkin_count``. Can be used as a performance optimization. Can be passed multiple times.
   :query string ordering: Manually set the ordering of results. Valid fields to be used are ``id``, ``name``, and ``subevent__date_from``,
                           Default: ``subevent__date_from,name``
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/checkinlists/(id)/

   Returns information on one check-in list, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/checkinlists/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "name": "Default list",
        "checkin_count": 123,
        "position_count": 456,
        "all_products": true,
        "limit_products": [],
        "include_pending": false,
        "subevent": null,
        "allow_multiple_entries": false,
        "allow_entry_after_exit": true,
        "exit_all_at": null,
        "rules": {},
        "addon_match": false
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the check-in list to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/checkinlists/(id)/status/

   Returns detailed status information on a check-in list, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/checkinlists/1/status/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "checkin_count": 17,
        "position_count": 42,
        "inside_count": 12,
        "event": {
          "name": "Demo Conference"
        },
        "items": [
          {
            "name": "T-Shirt",
            "id": 1,
            "checkin_count": 1,
            "admission": false,
            "position_count": 1,
            "variations": [
              {
                "value": "Red",
                "id": 1,
                "checkin_count": 1,
                "position_count": 12
              },
              {
                "value": "Blue",
                "id": 2,
                "checkin_count": 4,
                "position_count": 8
              }
            ]
          },
          {
            "name": "Ticket",
            "id": 2,
            "checkin_count": 15,
            "admission": true,
            "position_count": 22,
            "variations": []
          }
        ]
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the check-in list to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/checkinlists/

   Creates a new check-in list.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/checkinlists/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "name": "VIP entry",
        "all_products": false,
        "limit_products": [1, 2],
        "subevent": null,
        "allow_multiple_entries": false,
        "allow_entry_after_exit": true,
        "addon_match": false
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 2,
        "name": "VIP entry",
        "checkin_count": 0,
        "position_count": 0,
        "all_products": false,
        "limit_products": [1, 2],
        "include_pending": false,
        "subevent": null,
        "allow_multiple_entries": false,
        "allow_entry_after_exit": true,
        "addon_match": false
      }

   :param organizer: The ``slug`` field of the organizer of the event/item to create a list for
   :param event: The ``slug`` field of the event to create a list for
   :statuscode 201: no error
   :statuscode 400: The list could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/checkinlists/(id)/

   Update a check-in list. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   You can change all fields of the resource except the ``id`` field and the ``checkin_count`` and ``position_count``
   fields.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/checkinlists/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "name": "Backstage",
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 2,
        "name": "Backstage",
        "checkin_count": 23,
        "position_count": 42,
        "all_products": false,
        "limit_products": [1, 2],
        "include_pending": false,
        "subevent": null,
        "allow_multiple_entries": false,
        "allow_entry_after_exit": true,
        "addon_match": false
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the list to modify
   :statuscode 200: no error
   :statuscode 400: The list could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to change this resource.

.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/checkinlist/(id)/

   Delete a check-in list. **Note that this also deletes the information on all check-ins performed via this list.**

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/checkinlist/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the check-in list to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to delete this resource.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/checkinlists/(list)/failed_checkins/

   Stores a failed check-in. Only necessary for statistical purposes if you perform scan validation offline.

   :<json boolean error_reason: One of ``canceled``, ``invalid``, ``unpaid``, ``product``, ``rules``, ``revoked``,
                                ``incomplete``, ``already_redeemed``, ``blocked``, ``invalid_time``, or ``error``. Required.
   :<json raw_barcode: The raw barcode you scanned. Required.
   :<json datetime: Date and time of the scan. Optional.
   :<json type: Type of scan, defaults to ``"entry"``.
   :<json position: Internal ID of an order position you matched. Optional.
   :<json raw_item: Internal ID of an item you matched. Optional.
   :<json raw_variation: Internal ID of an item variation you matched. Optional.
   :<json raw_subevent: Internal ID of an event series date you matched. Optional.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/checkinlists/1/failed_checkins/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

      {
        "raw_barcode": "Pvrk50vUzQd0DhdpNRL4I4OcXsvg70uA",
        "error_reason": "canceled"
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param list: The ID of the check-in list to save for
   :statuscode 201: no error
   :statuscode 400: Invalid request
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order position or check-in list does not exist.


Order position endpoints
------------------------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/checkinlists/(list)/positions/

   Returns a list of all order positions within a given event. The result is the same as
   the :ref:`order-position-resource`, with the following differences:

   * The ``checkins`` value will only include check-ins for the selected list.

   * An additional boolean property ``require_attention`` will inform you whether either the order or the item
     have the ``checkin_attention`` flag set.

   * If ``attendee_name`` is empty, it will automatically fall back to values from a parent product or from invoice
     addresses.

   You can use this endpoint to implement a ticket search. We also provide a dedicated search input as part of our
   :ref:`check-in API <rest-checkin>` that supports search across multiple events.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/checkinlists/1/positions/ HTTP/1.1
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
            "id": 23442,
            "order": "ABC12",
            "positionid": 1,
            "item": 1345,
            "variation": null,
            "price": "23.00",
            "attendee_name": "Peter",
            "attendee_name_parts": {
              "full_name": "Peter",
            },
            "attendee_email": null,
            "voucher": null,
            "tax_rate": "0.00",
            "tax_rule": null,
            "tax_value": "0.00",
            "secret": "z3fsn8jyufm5kpk768q69gkbyr5f4h6w",
            "addon_to": null,
            "subevent": null,
            "pseudonymization_id": "MQLJvANO3B",
            "seat": null,
            "checkins": [
              {
                "list": 1,
                "type": "entry",
                "gate": null,
                "device": 2,
                "datetime": "2017-12-25T12:45:23Z",
                "auto_checked_in": true
              }
            ],
            "answers": [
              {
                "question": 12,
                "answer": "Foo",
                "options": []
              }
            ],
            "downloads": [
              {
                "output": "pdf",
                "url": "https://pretix.eu/api/v1/organizers/bigevents/events/sampleconf/orderpositions/23442/download/pdf/"
              }
            ]
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query string ignore_status: If set to ``true``, results will be returned regardless of the state of
                                 the order they belong to and you will need to do your own filtering by order status.
   :query string ordering: Manually set the ordering of results. Valid fields to be used are ``order__code``,
                           ``order__datetime``, ``positionid``, ``attendee_name``, ``last_checked_in`` and ``order__email``. Default:
                           ``attendee_name,positionid``
   :query string order: Only return positions of the order with the given order code
   :query string search: Fuzzy search matching the attendee name, order code, invoice address name as well as to the beginning of the secret.
   :query string expand: Expand a field into a full object. Currently ``subevent``, ``item``, ``variation``, and ``answers.question`` are supported. Can be passed multiple times.
   :query integer item: Only return positions with the purchased item matching the given ID.
   :query integer item__in: Only return positions with the purchased item matching one of the given comma-separated IDs.
   :query integer variation: Only return positions with the purchased item variation matching the given ID.
   :query integer variation__in: Only return positions with one of the purchased item variation matching the given
                                 comma-separated IDs.
   :query string attendee_name: Only return positions with the given value in the attendee_name field. Also, add-on
                                products positions are shown if they refer to an attendee with the given name.
   :query string secret: Only return positions with the given ticket secret.
   :query string order__status: Only return positions with the given order status.
   :query string order__status__in: Only return positions with one the given comma-separated order status.
   :query boolean has_checkin: If set to ``true`` or ``false``, only return positions that have or have not been
                               checked in already.
   :query integer subevent: Only return positions of the sub-event with the given ID
   :query integer subevent__in: Only return positions of one of the sub-events with the given comma-separated IDs
   :query integer addon_to: Only return positions that are add-ons to the position with the given ID.
   :query integer addon_to__in: Only return positions that are add-ons to one of the positions with the given
                                      comma-separated IDs.
   :query string voucher: Only return positions with a specific voucher.
   :query string voucher__code: Only return positions with a specific voucher code.
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param list: The ID of the check-in list to look for
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested check-in list does not exist.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/checkinlists/(list)/positions/(id)/

   Returns information on one order position, identified by its internal ID.
   The result is the same as the :ref:`order-position-resource`, with the following differences:

   * The ``checkins`` value will only include check-ins for the selected list.

   * An additional boolean property ``require_attention`` will inform you whether either the order or the item
     have the ``checkin_attention`` flag set.

   * If ``attendee_name`` is empty, it will automatically fall back to values from a parent product or from invoice
     addresses.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/checkinlists/1/positions/23442/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 23442,
        "order": "ABC12",
        "positionid": 1,
        "item": 1345,
        "variation": null,
        "price": "23.00",
        "attendee_name": "Peter",
        "attendee_name_parts": {
          "full_name": "Peter",
        },
        "attendee_email": null,
        "voucher": null,
        "tax_rate": "0.00",
        "tax_rule": null,
        "tax_value": "0.00",
        "secret": "z3fsn8jyufm5kpk768q69gkbyr5f4h6w",
        "addon_to": null,
        "subevent": null,
        "pseudonymization_id": "MQLJvANO3B",
        "seat": null,
        "checkins": [
          {
            "list": 1,
            "datetime": "2017-12-25T12:45:23Z",
            "type": "entry",
            "gate": null,
            "device": 2,
            "auto_checked_in": true
          }
        ],
        "answers": [
          {
            "question": 12,
            "answer": "Foo",
            "options": []
          }
        ],
        "downloads": [
          {
            "output": "pdf",
            "url": "https://pretix.eu/api/v1/organizers/bigevents/events/sampleconf/orderpositions/23442/download/pdf/"
          }
        ]
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param list: The ID of the check-in list to look for
   :param id: The ``id`` field of the order position to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order position or check-in list does not exist.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/checkinlists/(list)/positions/(id)/redeem/

   Tries to redeem an order position, identified by its internal ID, i.e. checks the attendee in. This endpoint
   accepts a number of optional requests in the body.

   **Tip:** Instead of an ID, you can also use the ``secret`` field as the lookup parameter. In this case, you should
   always set ``untrusted_input=true`` as a query parameter to avoid security issues.

   .. note::

      We no longer recommend using this API if you're building a ticket scanning application, as it has a few design
      flaws that can lead to `security issues`_ or compatibility issues due to barcode content characters that are not
      URL-safe. We recommend to use our new :ref:`check-in API <rest-checkin>` instead.

   :query boolean untrusted_input: If set to true, the lookup parameter is **always** interpreted as a ``secret``, never
                                   as an ``id``. This should be always set if you are passing through untrusted, scanned
                                   data to avoid guessing of ticket IDs.
   :<json boolean questions_supported: When this parameter is set to ``true``, handling of questions is supported. If
                                       you do not implement question handling in your user interface, you **must**
                                       set this to ``false``. In that case, questions will just be ignored. Defaults
                                       to ``true``.
   :<json boolean canceled_supported: When this parameter is set to ``true``, the response code ``canceled`` may be
                                      returned. Otherwise, canceled orders will return ``unpaid``. (**Deprecated**, in
                                      the future, this will be ignored and ``canceled`` may always be returned.)
   :<json datetime datetime: Specifies the datetime of the check-in. If not supplied, the current time will be used.
   :<json boolean force: Specifies that the check-in should succeed regardless of revoked barcode, previous check-ins or required
                         questions that have not been filled. This is usually used to upload offline scans that already happened,
                         because there's no point in validating them since they happened whether they are valid or not. Defaults to ``false``.
   :<json string type: Send ``"exit"`` for an exit and ``"entry"`` (default) for an entry.
   :<json boolean ignore_unpaid: Specifies that the check-in should succeed even if the order is in pending state.
                                 Defaults to ``false`` and only works when ``include_pending`` is set on the check-in
                                 list.
   :<json string nonce: You can set this parameter to a unique random value to identify this check-in. If you're sending
                        this request twice with the same nonce, the second request will also succeed but will always
                        create only one check-in object even when the previous request was successful as well. This
                        allows for a certain level of idempotency and enables you to re-try after a connection failure.
   :<json object answers: If questions are supported/required, you may/must supply a mapping of question IDs to their
                          respective answers. The answers should always be strings. In case of (multiple-)choice-type
                          answers, the string should contain the (comma-separated) IDs of the selected options.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/checkinlists/1/positions/234/redeem/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

      {
        "force": false,
        "ignore_unpaid": false,
        "nonce": "Pvrk50vUzQd0DhdpNRL4I4OcXsvg70uA",
        "datetime": null,
        "questions_supported": true,
        "canceled_supported": true,
        "answers": {
          "4": "XS"
        }
      }

   **Example successful response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "status": "ok",
        "position": {
          …
        }
      }

   **Example response with required questions**:

   .. sourcecode:: http

      HTTP/1.1 400 Bad Request
      Content-Type: text/json

      {
        "status": "incomplete",
        "position": {
          …
        },
        "questions": [
          {
            "id": 1,
            "question": {"en": "T-Shirt size"},
            "type": "C",
            "required": false,
            "items": [1, 2],
            "position": 1,
            "identifier": "WY3TP9SL",
            "ask_during_checkin": true,
            "show_during_checkin": true,
            "options": [
              {
                "id": 1,
                "identifier": "LVETRWVU",
                "position": 0,
                "answer": {"en": "S"}
              },
              {
                "id": 2,
                "identifier": "DFEMJWMJ",
                "position": 1,
                "answer": {"en": "M"}
              },
              {
                "id": 3,
                "identifier": "W9AH7RDE",
                "position": 2,
                "answer": {"en": "L"}
              }
            ]
          }
        ]
      }

   **Example error response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: text/json

      {
        "status": "error",
        "reason": "unpaid",
        "position": {
          …
        }
      }

   Possible error reasons:

   * ``invalid`` - Ticket code not known.
   * ``unpaid`` - Ticket is not paid for.
   * ``blocked`` - Ticket has been blocked.
   * ``invalid_time`` - Ticket is not valid at this time.
   * ``canceled`` – Ticket is canceled or expired. This reason is only sent when your request sets.
     ``canceled_supported`` to ``true``, otherwise these orders return ``unpaid``.
   * ``already_redeemed`` - Ticket already has been redeemed.
   * ``product`` - Tickets with this product may not be scanned at this device.
   * ``rules`` - Check-in prevented by a user-defined rule.
   * ``ambiguous`` - Multiple tickets match scan, rejected.
   * ``revoked`` - Ticket code has been revoked.
   * ``unapproved`` - Order has not yet been approved.

   In case of reason ``rules`` or ``invalid_time``, there might be an additional response field ``reason_explanation``
   with a human-readable description of the violated rules. However, that field can also be missing or be ``null``.

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param list: The ID of the check-in list to look for
   :param id: The ``id`` field of the order position to fetch
   :statuscode 201: no error
   :statuscode 400: Invalid or incomplete request, see above
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order position or check-in list does not exist.


.. _security issues: https://pretix.eu/about/de/blog/20220705-release-4111/
