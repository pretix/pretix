.. _`rest-discounts`:

Discounts
=========

Resource description
--------------------

Discounts provide a way to automatically reduce the price of a cart if it matches a given set of conditions.
Discounts are available to everyone. If you want to give a discount just to specific persons, look at
:ref:`vouchers <rest-vouchers>` instead. If you are interested in the behind-the-scenes details of how
discounts are calculated for a specific order, have a look at :ref:`our algorithm documentation <algorithms-pricing>`.

.. rst-class:: rest-resource-table

======================================== ========================== =======================================================
Field                                    Type                       Description
======================================== ========================== =======================================================
id                                       integer                    Internal ID of the discount rule
active                                   boolean                    The discount will be ignored if this is ``false``
internal_name                            string                     A name for the rule used in the backend
position                                 integer                    An integer, used for sorting the rules which are applied in order
all_sales_channels                       boolean                    If ``true`` (default), the discount is available on all sales channels
                                                                    that support discounts.
limit_sales_channels                     list of strings            List of sales channel identifiers the discount is available on
                                                                    if ``all_sales_channels`` is ``false``.
sales_channels                           list of strings            **DEPRECATED.** Legacy interface, use ``all_sales_channels``
                                                                    and ``limit_sales_channels`` instead.
available_from                           datetime                   The first date time at which this discount can be applied
                                                                    (or ``null``).
available_until                          datetime                   The last date time at which this discount can be applied
                                                                    (or ``null``).
subevent_mode                            strings                    Determines how the discount is handled when used in an
                                                                    event series. Can be ``"mixed"`` (no special effect),
                                                                    ``"same"`` (discount is only applied for groups within
                                                                    the same date), or ``"distinct"`` (discount is only applied
                                                                    for groups with no two same dates).
subevent_date_from                       datetime                   The first date time of a subevent to which this discount can be applied
                                                                    (or ``null``). Ignored in non-series events.
subevent_date_until                      datetime                   The last date time of a subevent to which this discount can be applied
                                                                    (or ``null``). Ignored in non-series events.
condition_all_products                   boolean                    If ``true``, the discount condition applies to all items.
condition_limit_products                 list of integers           If ``condition_all_products`` is not set, this is a list
                                                                    of internal item IDs that the discount condition applies to.
condition_apply_to_addons                boolean                    If ``true``, the discount applies to add-on products as well,
                                                                    otherwise it only applies to top-level items. The discount never
                                                                    applies to bundled products.
condition_ignore_voucher_discounted      boolean                    If ``true``, the discount does not apply to products which have
                                                                    been discounted by a voucher.
condition_min_count                      integer                    The minimum number of matching products for the discount
                                                                    to be activated.
condition_min_value                      money (string)             The minimum value of matching products for the discount
                                                                    to be activated. Cannot be combined with ``condition_min_count``,
                                                                    or with ``subevent_mode`` set to ``distinct``.
benefit_discount_matching_percent        decimal (string)           The percentage of price reduction for matching products.
benefit_only_apply_to_cheapest_n_matches integer                    If set higher than 0, the discount will only be applied to
                                                                    the cheapest matches. Useful for a "3 for 2"-style discount.
                                                                    Cannot be combined with ``condition_min_value``.
benefit_same_products                    boolean                    If ``true``, the discount benefit applies to the same set of items
                                                                    as the condition (see above).
benefit_limit_products                   list of integers           If ``benefit_same_products`` is not set, this is a list
                                                                    of internal item IDs that the discount benefit applies to.
benefit_apply_to_addons                  boolean                    (Only used if ``benefit_same_products`` is ``false``.)
                                                                    If ``true``, the discount applies to add-on products as well,
                                                                    otherwise it only applies to top-level items. The discount never
                                                                    applies to bundled products.
benefit_ignore_voucher_discounted        boolean                    (Only used if ``benefit_same_products`` is ``false``.)
                                                                    If ``true``, the discount does not apply to products which have
                                                                    been discounted by a voucher.
======================================== ========================== =======================================================


Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/discounts/

   Returns a list of all discounts within a given event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/discounts/ HTTP/1.1
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
            "active": true,
            "internal_name": "3 for 2",
            "position": 1,
            "all_sales_channels": false,
            "limit_sales_channels": ["web"],
            "sales_channels": ["web"],
            "available_from": null,
            "available_until": null,
            "subevent_mode": "mixed",
            "subevent_date_from": null,
            "subevent_date_until": null,
            "condition_all_products": true,
            "condition_limit_products": [],
            "condition_apply_to_addons": true,
            "condition_ignore_voucher_discounted": false,
            "condition_min_count": 3,
            "condition_min_value": "0.00",
            "benefit_same_products": true,
            "benefit_limit_products": [],
            "benefit_apply_to_addons": true,
            "benefit_ignore_voucher_discounted": false,
            "benefit_discount_matching_percent": "100.00",
            "benefit_only_apply_to_cheapest_n_matches": 1
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query boolean active: If set to ``true`` or ``false``, only discounts with this value for the field ``active`` will be
                          returned.
   :query string ordering: Manually set the ordering of results. Valid fields to be used are ``id`` and ``position``.
                           Default: ``position``
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/discounts/(id)/

   Returns information on one discount, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/discounts/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "active": true,
        "internal_name": "3 for 2",
        "position": 1,
        "all_sales_channels": false,
        "limit_sales_channels": ["web"],
        "sales_channels": ["web"],
        "available_from": null,
        "available_until": null,
        "subevent_mode": "mixed",
        "subevent_date_from": null,
        "subevent_date_until": null,
        "condition_all_products": true,
        "condition_limit_products": [],
        "condition_apply_to_addons": true,
        "condition_ignore_voucher_discounted": false,
        "condition_min_count": 3,
        "condition_min_value": "0.00",
        "benefit_same_products": true,
        "benefit_limit_products": [],
        "benefit_apply_to_addons": true,
        "benefit_ignore_voucher_discounted": false,
        "benefit_discount_matching_percent": "100.00",
        "benefit_only_apply_to_cheapest_n_matches": 1
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the discount to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/discounts/

   Creates a new discount

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/discounts/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "active": true,
        "internal_name": "3 for 2",
        "position": 1,
        "all_sales_channels": false,
        "limit_sales_channels": ["web"],
        "sales_channels": ["web"],
        "available_from": null,
        "available_until": null,
        "subevent_mode": "mixed",
        "subevent_date_from": null,
        "subevent_date_until": null,
        "condition_all_products": true,
        "condition_limit_products": [],
        "condition_apply_to_addons": true,
        "condition_ignore_voucher_discounted": false,
        "condition_min_count": 3,
        "condition_min_value": "0.00",
        "benefit_same_products": true,
        "benefit_limit_products": [],
        "benefit_apply_to_addons": true,
        "benefit_ignore_voucher_discounted": false,
        "benefit_discount_matching_percent": "100.00",
        "benefit_only_apply_to_cheapest_n_matches": 1
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "active": true,
        "internal_name": "3 for 2",
        "position": 1,
        "all_sales_channels": false,
        "limit_sales_channels": ["web"],
        "sales_channels": ["web"],
        "available_from": null,
        "available_until": null,
        "subevent_mode": "mixed",
        "subevent_date_from": null,
        "subevent_date_until": null,
        "condition_all_products": true,
        "condition_limit_products": [],
        "condition_apply_to_addons": true,
        "condition_ignore_voucher_discounted": false,
        "condition_min_count": 3,
        "condition_min_value": "0.00",
        "benefit_same_products": true,
        "benefit_limit_products": [],
        "benefit_apply_to_addons": true,
        "benefit_ignore_voucher_discounted": false,
        "benefit_discount_matching_percent": "100.00",
        "benefit_only_apply_to_cheapest_n_matches": 1
      }

   :param organizer: The ``slug`` field of the organizer of the event to create a discount for
   :param event: The ``slug`` field of the event to create a discount for
   :statuscode 201: no error
   :statuscode 400: The discount could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/discounts/(id)/

   Update a discount. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   You can change all fields of the resource except the ``id`` field.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/discounts/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "active": false
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "active": false,
        "internal_name": "3 for 2",
        "position": 1,
        "all_sales_channels": false,
        "limit_sales_channels": ["web"],
        "sales_channels": ["web"],
        "available_from": null,
        "available_until": null,
        "subevent_mode": "mixed",
        "subevent_date_from": null,
        "subevent_date_until": null,
        "condition_all_products": true,
        "condition_limit_products": [],
        "condition_apply_to_addons": true,
        "condition_ignore_voucher_discounted": false,
        "condition_min_count": 3,
        "condition_min_value": "0.00",
        "benefit_same_products": true,
        "benefit_limit_products": [],
        "benefit_apply_to_addons": true,
        "benefit_ignore_voucher_discounted": false,
        "benefit_discount_matching_percent": "100.00",
        "benefit_only_apply_to_cheapest_n_matches": 1
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the discount to modify
   :statuscode 200: no error
   :statuscode 400: The discount could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to change this resource.

.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/discount/(id)/

   Delete a discount.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/discount/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the discount to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to delete this resource.
