.. spelling:word-list:: checkin

.. _rest-checkin:

Check-in
========

This page describes special APIs built for ticket scanning apps. For managing check-in configuration or other operations,
please also see :ref:`rest-checkinlists`. The check-in list API also contains endpoints to obtain statistics or log
failed scans.

.. _`rest-checkin-redeem`:

Checking a ticket in
--------------------

.. http:post:: /api/v1/organizers/(organizer)/checkinrpc/redeem/

   Tries to redeem an order position, i.e. checks the attendee in (or out). This is the recommended endpoint to use
   if you build any kind of scanning app that performs check-ins for scanned barcodes. It is safe to use with untrusted
   inputs in the ``secret`` field.

   This endpoint supports passing multiple check-in lists to perform a multi-event scan. However, each check-in list
   passed needs to be from a distinct event.

   :query string expand: Expand a field inside the ``position`` object into a full object. Currently ``subevent``, ``item``, ``variation``, and ``answers.question`` are supported. Can be passed multiple times.
   :<json string secret: Scanned QR code corresponding to the ``secret`` attribute of a ticket.
   :<json string source_type: Type of source the ``secret`` was obtained form. Defaults to ``"barcode"``.
   :<json array lists: List of check-in list IDs to search on. No two check-in lists may be from the same event.
   :<json string type: Send ``"exit"`` for an exit and ``"entry"`` (default) for an entry.
   :<json datetime datetime: Specifies the datetime of the check-in. If not supplied, the current time will be used.
   :<json boolean force: Specifies that the check-in should succeed regardless of revoked barcode, previous check-ins or required
                         questions that have not been filled. This is usually used to upload offline scans that already happened,
                         because there's no point in validating them since they happened whether they are valid or not. Defaults to ``false``.
   :<json boolean questions_supported: When this parameter is set to ``true``, handling of questions is supported. If
                                       you do not implement question handling in your user interface, you **must**
                                       set this to ``false``. In that case, questions will just be ignored. Defaults
                                       to ``true``.
   :<json boolean ignore_unpaid: Specifies that the check-in should succeed even if the order is in pending state.
                                 Defaults to ``false`` and only works when ``include_pending`` is set on the check-in
                                 list.
   :<json object answers: If questions are supported/required, you may/must supply a mapping of question IDs to their
                          respective answers. The answers should always be strings. In case of (multiple-)choice-type
                          answers, the string should contain the (comma-separated) IDs of the selected options.
   :<json string nonce: You can set this parameter to a unique random value to identify this check-in. If you're sending
                        this request twice with the same nonce, the second request will also succeed but will always
                        create only one check-in object even when the previous request was successful as well. This
                        allows for a certain level of idempotency and enables you to re-try after a connection failure.
   :<json boolean use_order_locale: Specifies that pretix should use the customer's language (``locale`` field from the
                                    order) when building texts (currently only the ``reason_explanation`` response field).
                                    Defaults to ``false`` in which case the server will determine the language (currently
                                    the event default language, might change in the future with support for the
                                    ``Accept-Language`` header).
   :>json string status: ``"ok"``, ``"incomplete"``, or ``"error"``
   :>json string reason: Reason code, only set on status ``"error"``, see below for possible values.
   :>json string reason_explanation: Human-readable explanation, only set on status ``"error"`` and reason ``"rules"``, can be null.
   :>json object position: Copy of the matching order position (if any was found). The contents are the same as the
                           :ref:`order-position-resource`, with the following differences: (1) The ``checkins`` value
                           will only include check-ins for the selected list. (2) An additional boolean property
                           ``require_attention`` will inform you whether either the order or the item have the
                           ``checkin_attention`` flag set. (3) If ``attendee_name`` is empty, it may automatically fall
                           back to values from a parent product or from invoice addresses. (4) Additional properties
                           ``order__status``, ``order__valid_if_pending``, ``order__require_approval``, and
                           ``order__locale`` are included with details form the order for convenience.
   :>json boolean require_attention: Whether or not the ``require_attention`` flag is set on the item or order.
   :>json list checkin_texts: List of additional texts to show to the user.
   :>json object list: Excerpt of information about the matching :ref:`check-in list <rest-checkinlists>` (if any was found),
                       including the attributes ``id``, ``name``, ``event``, ``subevent``, and ``include_pending``.
   :>json object questions: List of questions to be answered for check-in, only set on status ``"incomplete"``.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/checkinrpc/redeem/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

      {
        "secret": "M5BO19XmFwAjLd4nDYUAL9ISjhti0e9q",
        "source_type": "barcode",
        "lists": [1],
        "force": false,
        "ignore_unpaid": false,
        "nonce": "Pvrk50vUzQd0DhdpNRL4I4OcXsvg70uA",
        "datetime": null,
        "questions_supported": true,
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
        },
        "require_attention": false,
        "checkin_texts": [],
        "list": {
          "id": 1,
          "name": "Default check-in list",
          "event": "sampleconf",
          "subevent": null,
          "include_pending": false
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
        "require_attention": false,
        "checkin_texts": [],
        "list": {
          "id": 1,
          "name": "Default check-in list",
          "event": "sampleconf",
          "subevent": null,
          "include_pending": false
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

   **Example error response (invalid ticket)**:

   .. sourcecode:: http

      HTTP/1.1 404 Not Found
      Content-Type: text/json

      {
        "detail": "Not found.",
        "status": "error",
        "reason": "invalid",
        "reason_explanation": null,
        "require_attention": false,
        "checkin_texts": []
      }

   **Example error response (known, but invalid ticket)**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: text/json

      {
        "status": "error",
        "reason": "unpaid",
        "reason_explanation": null,
        "require_attention": false,
        "checkin_texts": [],
        "list": {
          "id": 1,
          "name": "Default check-in list",
          "event": "sampleconf",
          "subevent": null,
          "include_pending": false
        },
        "position": {
          …
        }
      }

   Possible error reasons:

   * ``invalid`` - Ticket is not known.
   * ``unpaid`` - Ticket is not paid for.
   * ``blocked`` - Ticket has been blocked.
   * ``invalid_time`` - Ticket is not valid at this time.
   * ``canceled`` – Ticket is canceled or expired.
   * ``already_redeemed`` - Ticket already has been redeemed.
   * ``product`` - Tickets with this product may not be scanned at this device.
   * ``rules`` - Check-in prevented by a user-defined rule.
   * ``ambiguous`` - Multiple tickets match scan, rejected.
   * ``revoked`` - Ticket code has been revoked.
   * ``unapproved`` - Order has not yet been approved.
   * ``error`` - Internal error.

   In case of reason ``rules`` and ``invalid_time``, there might be an additional response field ``reason_explanation``
   with a human-readable description of the violated rules. However, that field can also be missing or be ``null``.

   :param organizer: The ``slug`` field of the organizer to fetch
   :statuscode 201: no error
   :statuscode 400: Invalid or incomplete request, see above
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order position does not exist.

Performing a ticket search
--------------------------

.. http:get:: /api/v1/organizers/(organizer)/checkinrpc/search/

   Returns a list of all order positions matching a given search request. The result is the same as
   the :ref:`order-position-resource`, with the following differences:

   * The ``checkins`` value will only include check-ins for the selected list.

   * An additional boolean property ``require_attention`` will inform you whether either the order or the item
     have the ``checkin_attention`` flag set.

   * If ``attendee_name`` is empty, it will automatically fall back to values from a parent product or from invoice
     addresses.

   This endpoint supports passing multiple check-in lists to perform a multi-event search. However, each check-in list
   passed needs to be from a distinct event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/checkinrpc/search/?list=1&search=Peter HTTP/1.1
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

   :query string search: Fuzzy search matching the attendee name, order code, invoice address name as well as to the beginning of the secret.
   :query integer list: The check-in list to search on, can be passed multiple times.
   :query integer page: The page number in case of a multi-page result set, default is 1
   :query string ignore_status: If set to ``true``, results will be returned regardless of the state of
                                 the order they belong to and you will need to do your own filtering by order status.
   :query string ordering: Manually set the ordering of results. Valid fields to be used are ``order__code``,
                           ``order__datetime``, ``positionid``, ``attendee_name``, ``last_checked_in`` and ``order__email``. Default:
                           ``attendee_name,positionid``
   :query string order: Only return positions of the order with the given order code
   :query string search: Fuzzy search matching the attendee name, order code, invoice address name as well as to the beginning of the secret.
   :query string expand: Expand a field into a full object. Currently only ``subevent``, ``item``, and ``variation`` are supported. Can be passed multiple times.
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
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or check-in list does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested check-in list does not exist.

.. _`rest-checkin-annul`:

Annulment of a check-in
-----------------------

.. http:post:: /api/v1/organizers/(organizer)/checkinrpc/annul/

   If a check-in was made in error and the person was not let in, it can be annulled. We do not recommend this to be used
   in case of manual check-ins or user interfaces because it is too prone for human errors. It is mostly intended for
   automated entry systems like a turnstile or automated door, where the check-in is first created, then the door is
   opened, and then the check-in may be annulled if the system knows that the turnstile did not turn or was out of
   order.

   This endpoint supports passing multiple check-in lists for the context of a multi-event scan. However, each
   check-in list passed needs to be from a distinct event.

   Check-ins created by a device can only be annulled by the same device. The datetime of annulment may not be more than
   15 minutes after the datetime of check-in (value subject to change).

   A status code of 404 is returned if no check-in was found for the given nonce. A status code of 400 is returned when
   multiple check-ins match the nonce, the input is invalid in another way, the annulment is made from the wrong device,
   the check-in is already in an annulled or failed state, or the datetime constraint is not valid.

   :<json string nonce: ``nonce`` value of the original check-in.
   :<json array lists: List of check-in list IDs to search on. No two check-in lists may be from the same event.
   :<json datetime datetime: Specifies the client-side datetime of the annulment. If not supplied, the current time will be used.
   :<json string error_explanation: A human-readable description of why the check-in was annulled (optional).
   :>json string status: ``"ok"``

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/checkinrpc/annul/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

      {
        "lists": [1],
        "nonce": "Pvrk50vUzQd0DhdpNRL4I4OcXsvg70uA",
        "error_explanation": "Turnstile did not turn"
      }

   **Example successful response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "status": "ok",
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :statuscode 200: no error
   :statuscode 400: Invalid or incomplete request, see above
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested nonce does not exist.


Check-in history
----------------

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the check-in
successful                            boolean                    Whether the check-in was successful
error_reason                          string                     Category of reason why the check-in was unsuccessful. Currently
                                                                 ``"canceled"``, ``"invalid"``, ``"unpaid"`` ``"product"``,
                                                                 ``"rules"``, ``"revoked"``, ``"incomplete"``, ``"already_redeemed"``,
                                                                 ``"ambiguous"``, ``"error"``, ``"blocked"``, ``"unapproved"``,
                                                                 ``"invalid_time"``, ``"annulled"`` or ``null``
error_explanation                     string                     Additional, human-readable reason for the check-in to be unsuccessful (or ``null``)
position                              integer                    Internal ID of the order position (or ``null`` for unknown scans)
datetime                              datetime                   Logical time when the check-in happened
created                               datetime                   Time when the check-in appeared on the server
list                                  integer                    Internal ID of the check-in list
auto_checked_in                       boolean                    Whether the check-in was performed by the system automatically
gate                                  integer                    Internal ID of the gate (or ``null``)
device                                integer                    Internal ID of the device (or ``null``)
device_id                             integer                    Organizer-internal ID of the device (or ``null``)
type                                  string                     Type of check-in, currently ``"entry"`` or ``"exit"``
===================================== ========================== =======================================================

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/checkins/

   Returns a list of all check-in events within a given event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/checkins/ HTTP/1.1
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
            "successful": true,
            "error_reason": null,
            "error_explanation": null,
            "position": 1234,
            "datetime": "2017-12-25T12:45:23Z",
            "created": "2017-12-25T12:45:23Z",
            "list": 2,
            "auto_checked_in": false,
            "gate": null,
            "device": null,
            "device_id": null,
            "type": "entry",
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query datetime created_since: Only return check-ins that have been created since the given date (inclusive).
   :query datetime created_before: Only return check-ins that have been created before the given date (exclusive).
   :query datetime datetime_since: Only return check-ins that have happened since the given date (inclusive).
   :query datetime datetime_before: Only return check-ins that have happened before the given date (exclusive).
   :query boolean successful: Only return check-ins that have (not) been successful.
   :query boolean error_reason: Only return check-ins with a specific error reason.
   :query integer list: Only return check-ins from a specific list.
   :query string type: Only return check-ins of a specific type.
   :query integer gate: Only return check-ins from a specific gate.
   :query integer device: Only return check-ins from a specific device.
   :query boolean auto_checked_in: Only return check-ins that are (not) auto-checked in.
   :query string ordering: Manually set the ordering of results. Valid fields to be used are ``datetime``, ``created``,
                           and ``id``.
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
