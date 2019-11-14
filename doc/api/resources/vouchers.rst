Vouchers
========

Resource description
--------------------

The voucher resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the voucher
code                                  string                     The voucher code that is required to redeem the voucher
max_usages                            integer                    The maximum number of times this voucher can be
                                                                 redeemed (default: 1).
redeemed                              integer                    The number of times this voucher already has been
                                                                 redeemed.
valid_until                           datetime                   The voucher expiration date (or ``null``).
block_quota                           boolean                    If ``true``, quota is blocked for this voucher.
allow_ignore_quota                    boolean                    If ``true``, this voucher can be redeemed even if a
                                                                 product is sold out and even if quota is not blocked
                                                                 for this voucher.
price_mode                            string                     Determines how this voucher affects product prices.
                                                                 Possible values:

                                                                 * ``none`` – No effect on price
                                                                 * ``set`` – The product price is set to the given ``value``
                                                                 * ``subtract`` – The product price is determined by the original price *minus* the given ``value``
                                                                 * ``percent`` – The product price is determined by the original price reduced by the percentage given in ``value``
value                                 decimal (string)           The value (see ``price_mode``)
item                                  integer                    An ID of an item this voucher is restricted to (or ``null``)
variation                             integer                    An ID of a variation this voucher is restricted to (or ``null``)
quota                                 integer                    An ID of a quota this voucher is restricted to  (or
                                                                 ``null``). This is an exclusive alternative to
                                                                 ``item`` and ``variation``: A voucher can be
                                                                 attached either to a specific product or to all
                                                                 products within one quota or it can be available
                                                                 for all items without restriction.
seat                                  string                     ``seat_guid`` attribute of a specific seat (or ``null``)
tag                                   string                     A string that is used for grouping vouchers
comment                               string                     An internal comment on the voucher
subevent                              integer                    ID of the date inside an event series this voucher belongs to (or ``null``).
show_hidden_items                     boolean                    Only if set to ``true``, this voucher allows to buy products with the property ``hide_without_voucher``. Defaults to ``true``.
===================================== ========================== =======================================================


.. versionchanged:: 1.9

   The write operations ``POST``, ``PATCH``, ``PUT``, and ``DELETE`` have been added.

.. versionchanged:: 3.0

   The attribute ``show_hidden_items`` has been added.

.. versionchanged:: 3.4

   The attribute ``seat`` has been added.

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/vouchers/

   Returns a list of all vouchers within a given event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/vouchers/ HTTP/1.1
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
            "code": "43K6LKM37FBVR2YG",
            "max_usages": 1,
            "redeemed": 0,
            "valid_until": null,
            "block_quota": false,
            "allow_ignore_quota": false,
            "price_mode": "set",
            "value": "12.00",
            "item": 1,
            "variation": null,
            "quota": null,
            "tag": "testvoucher",
            "comment": "",
            "seat": null,
            "subevent": null,
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query string code: Only show the voucher with the given voucher code.
   :query integer max_usages: Only show vouchers with the given maximal number of usages.
   :query integer redeemed: Only show vouchers with the given number of redemptions. Note that this doesn't tell you if
                            the voucher can still be redeemed, as this also depends on ``max_usages``. See the
                            ``active`` query parameter as well.
   :query boolean block_quota: If set to ``true`` or ``false``, only vouchers with this value in the field
                               ``block_quota`` will be shown.
   :query boolean allow_ignore_quota: If set to ``true`` or ``false``, only vouchers with this value in the field
                                      ``allow_ignore_quota`` will be shown.
   :query string price_mode: If set, only vouchers with this value in the field ``price_mode`` will be shown (see
                             above).
   :query string value: If set, only vouchers with this value in the field ``value`` will be shown.
   :query integer item: If set, only vouchers attached to the item with the given ID will be shown.
   :query integer variation: If set, only vouchers attached to the variation with the given ID will be shown.
   :query integer quota: If set, only vouchers attached to the quota with the given ID will be shown.
   :query string tag: If set, only vouchers with the given tag will be shown.
   :query integer subevent: Only return vouchers of the sub-event with the given ID
   :query string ordering: Manually set the ordering of results. Valid fields to be used are ``id``, ``code``,
                           ``max_usages``, ``valid_until``, and ``value``. Default: ``id``
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/vouchers/(id)/

   Returns information on one voucher, identified by its internal ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/vouchers/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "code": "43K6LKM37FBVR2YG",
        "max_usages": 1,
        "redeemed": 0,
        "valid_until": null,
        "block_quota": false,
        "allow_ignore_quota": false,
        "price_mode": "set",
        "value": "12.00",
        "item": 1,
        "variation": null,
        "quota": null,
        "tag": "testvoucher",
        "comment": "",
        "seat": null,
        "subevent": null
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the voucher to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/vouchers/

   Create a new voucher.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/vouchers/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 408

      {
        "code": "43K6LKM37FBVR2YG",
        "max_usages": 1,
        "valid_until": null,
        "block_quota": false,
        "allow_ignore_quota": false,
        "price_mode": "set",
        "value": "12.00",
        "item": 1,
        "variation": null,
        "quota": null,
        "tag": "testvoucher",
        "comment": "",
        "subevent": null
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "code": "43K6LKM37FBVR2YG",
        "max_usages": 1,
        "redeemed": 0,
        "valid_until": null,
        "block_quota": false,
        "allow_ignore_quota": false,
        "price_mode": "set",
        "value": "12.00",
        "item": 1,
        "variation": null,
        "quota": null,
        "tag": "testvoucher",
        "comment": "",
        "seat": null,
        "subevent": null
      }

   :param organizer: The ``slug`` field of the organizer to create a voucher for
   :param event: The ``slug`` field of the event to create a voucher for
   :statuscode 201: no error
   :statuscode 400: The voucher could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this resource.
   :statuscode 409: The server was unable to acquire a lock and could not process your request. You can try again after a short waiting period.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/vouchers/batch_create/

   Creates multiple new vouchers atomically.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/vouchers/batch_create/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 408

      [
        {
          "code": "43K6LKM37FBVR2YG",
          "max_usages": 1,
          "valid_until": null,
          "block_quota": false,
          "allow_ignore_quota": false,
          "price_mode": "set",
          "value": "12.00",
          "item": 1,
          "variation": null,
          "quota": null,
          "tag": "testvoucher",
          "comment": "",
          "subevent": null
        },
        {
          "code": "ASDKLJCYXCASDASD",
          "max_usages": 1,
          "valid_until": null,
          "block_quota": false,
          "allow_ignore_quota": false,
          "price_mode": "set",
          "value": "12.00",
          "item": 1,
          "variation": null,
          "quota": null,
          "tag": "testvoucher",
          "comment": "",
          "subevent": null
        },

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      [
        {
          "id": 1,
          "code": "43K6LKM37FBVR2YG",
          …
        }, …
      }

   :param organizer: The ``slug`` field of the organizer to create a vouchers for
   :param event: The ``slug`` field of the event to create a vouchers for
   :statuscode 201: no error
   :statuscode 400: The vouchers could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this resource.
   :statuscode 409: The server was unable to acquire a lock and could not process your request. You can try again after a short waiting period.

.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/vouchers/(id)/

   Update a voucher. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   You can change all fields of the resource except the ``id`` and ``redeemed`` fields.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/vouchers/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 408

      {
        "price_mode": "set",
        "value": "24.00"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "code": "43K6LKM37FBVR2YG",
        "max_usages": 1,
        "redeemed": 0,
        "valid_until": null,
        "block_quota": false,
        "allow_ignore_quota": false,
        "price_mode": "set",
        "value": "24.00",
        "item": 1,
        "variation": null,
        "quota": null,
        "tag": "testvoucher",
        "comment": "",
        "seat": null,
        "subevent": null
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the voucher to modify
   :statuscode 200: no error
   :statuscode 400: The voucher could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to change this resource.
   :statuscode 409: The server was unable to acquire a lock and could not process your request. You can try again after a short waiting period.

.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/vouchers/(id)/

   Delete a voucher. Note that you cannot delete a voucher if it already has been redeemed.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/vouchers/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the voucher to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to delete this resource.
