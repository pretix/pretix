.. _rest-items:

Items
=====

Resource description
--------------------

Items (better known as products) are the things that can be sold using pretix.
The item resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the item
name                                  multi-lingual string       The item's visible name
internal_name                         string                     An optional name that is only used in the backend
default_price                         money (string)             The item price that is applied if the price is not
                                                                 overwritten by variations or other options.
category                              integer                    The ID of the category this item belongs to
                                                                 (or ``null``).
active                                boolean                    If ``False``, the item is hidden from all public lists
                                                                 and will not be sold.
description                           multi-lingual string       A public description of the item. May contain Markdown
                                                                 syntax or can be ``null``.
free_price                            boolean                    If ``True``, customers can change the price at which
                                                                 they buy the product (however, the price can't be set
                                                                 lower than the price defined by ``default_price`` or
                                                                 otherwise).
tax_rate                              decimal (string)           The VAT rate to be applied for this item.
tax_rule                              integer                    The internal ID of the applied tax rule (or ``null``).
admission                             boolean                    ``True`` for items that grant admission to the event
                                                                 (such as primary tickets) and ``False`` for others
                                                                 (such as add-ons or merchandise).
position                              integer                    An integer, used for sorting
picture                               string                     A product picture to be displayed in the shop
                                                                 (read-only).
sales_channels                        list of strings            Sales channels this product is available on, such as
                                                                 ``"web"`` or ``"resellers"``. Defaults to ``["web"]``.
available_from                        datetime                   The first date time at which this item can be bought
                                                                 (or ``null``).
available_until                       datetime                   The last date time at which this item can be bought
                                                                 (or ``null``).
require_voucher                       boolean                    If ``True``, this item can only be bought using a
                                                                 voucher that is specifically assigned to this item.
hide_without_voucher                  boolean                    If ``True``, this item is only shown during the voucher
                                                                 redemption process, but not in the normal shop
                                                                 frontend.
allow_cancel                          boolean                    If ``False``, customers cannot cancel orders containing
                                                                 this item.
min_per_order                         integer                    This product can only be bought if it is included at
                                                                 least this many times in the order (or ``null`` for no
                                                                 limitation).
max_per_order                         integer                    This product can only be bought if it is included at
                                                                 most this many times in the order (or ``null`` for no
                                                                 limitation).
checkin_attention                     boolean                    If ``True``, the check-in app should show a warning
                                                                 that this ticket requires special attention if such
                                                                 a product is being scanned.
original_price                        money (string)             An original price, shown for comparison, not used
                                                                 for price calculations.
require_approval                      boolean                    If ``True``, orders with this product will need to be
                                                                 approved by the event organizer before they can be
                                                                 paid.
generate_tickets                      boolean                    If ``False``, tickets are never generated for this
                                                                 product, regardless of other settings. If ``True``,
                                                                 tickets are generated even if this is a
                                                                 non-admission or add-on product, regardless of event
                                                                 settings. If this is ``null``, regular ticketing
                                                                 rules apply.
has_variations                        boolean                    Shows whether or not this item has variations.
variations                            list of objects            A list with one object for each variation of this item.
                                                                 Can be empty. Only writable during creation,
                                                                 use separate endpoint to modify this later.
├ id                                  integer                    Internal ID of the variation
├ value                               multi-lingual string       The "name" of the variation
├ default_price                       money (string)             The price set directly for this variation or ``null``
├ price                               money (string)             The price used for this variation. This is either the
                                                                 same as ``default_price`` if that value is set or equal
                                                                 to the item's ``default_price``.
├ active                              boolean                    If ``False``, this variation will not be sold or shown.
├ description                         multi-lingual string       A public description of the variation. May contain
                                                                 Markdown syntax or can be ``null``.
└ position                            integer                    An integer, used for sorting
addons                                list of objects            Definition of add-ons that can be chosen for this item.
                                                                 Only writable during creation,
                                                                 use separate endpoint to modify this later.
├ addon_category                      integer                    Internal ID of the item category the add-on can be
                                                                 chosen from.
├ min_count                           integer                    The minimal number of add-ons that need to be chosen.
├ max_count                           integer                    The maximal number of add-ons that can be chosen.
└ position                            integer                    An integer, used for sorting
└ price_included                      boolean                    Adding this add-on to the item is free
===================================== ========================== =======================================================

.. versionchanged:: 1.7

   The attribute ``tax_rule`` has been added. ``tax_rate`` is kept for compatibility. The attribute
   ``checkin_attention`` has been added.

.. versionchanged:: 1.12

   The write operations ``POST``, ``PATCH``, ``PUT``, and ``DELETE`` have been added.
   The attribute ``price_included`` has been added to ``addons``.

.. versionchanged:: 1.16

   The ``internal_name`` and ``original_price`` fields have been added.

.. versionchanged:: 2.0

   The field ``require_approval`` has been added.

.. versionchanged:: 2.3

   The ``sales_channels`` attribute has been added.

.. versionchanged:: 2.4

   The ``generate_tickets`` attribute has been added.

Notes
-----
Please note that an item either always has variations or never has. Once created with variations the item can never
change to an item without and vice versa. To create an item with variations ensure that you POST an item with at least
one variation.

Also note that ``variations`` and ``addons`` are only supported on ``POST``. To update/delete variations and add-ons please
use the dedicated nested endpoints. By design this endpoint does not support ``PATCH`` and ``PUT`` with nested
``variations`` and/or ``addons``.

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/items/

   Returns a list of all items within a given event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/items/ HTTP/1.1
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
            "name": {"en": "Standard ticket"},
            "internal_name": "",
            "sales_channels": ["web"],
            "default_price": "23.00",
            "original_price": null,
            "category": null,
            "active": true,
            "description": null,
            "free_price": false,
            "tax_rate": "0.00",
            "tax_rule": 1,
            "admission": false,
            "position": 0,
            "picture": null,
            "available_from": null,
            "available_until": null,
            "require_voucher": false,
            "hide_without_voucher": false,
            "allow_cancel": true,
            "min_per_order": null,
            "max_per_order": null,
            "checkin_attention": false,
            "has_variations": false,
            "generate_tickets": null,
            "require_approval": false,
            "variations": [
              {
                 "value": {"en": "Student"},
                 "default_price": "10.00",
                 "price": "10.00",
                 "active": true,
                 "description": null,
                 "position": 0
              },
              {
                 "value": {"en": "Regular"},
                 "default_price": null,
                 "price": "23.00",
                 "active": true,
                 "description": null,
                 "position": 1
              }
            ],
            "addons": []
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query boolean active: If set to ``true`` or ``false``, only items with this value for the field ``active`` will be
                          returned.
   :query integer category: If set to the ID of a category, only items within that category will be returned.
   :query boolean admission: If set to ``true`` or ``false``, only items with this value for the field ``admission``
                             will be returned.
   :query string tax_rate: If set to a decimal value, only items with this tax rate will be returned.
   :query boolean free_price: If set to ``true`` or ``false``, only items with this value for the field ``free_price``
                              will be returned.
   :query string ordering: Manually set the ordering of results. Valid fields to be used are ``id`` and ``position``.
                           Default: ``position``
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/items/(id)/

   Returns information on one item, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/items/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "name": {"en": "Standard ticket"},
        "internal_name": "",
        "sales_channels": ["web"],
        "default_price": "23.00",
        "original_price": null,
        "category": null,
        "active": true,
        "description": null,
        "free_price": false,
        "tax_rate": "0.00",
        "tax_rule": 1,
        "admission": false,
        "position": 0,
        "picture": null,
        "available_from": null,
        "available_until": null,
        "require_voucher": false,
        "hide_without_voucher": false,
        "allow_cancel": true,
        "generate_tickets": null,
        "min_per_order": null,
        "max_per_order": null,
        "checkin_attention": false,
        "has_variations": false,
        "require_approval": false,
        "variations": [
          {
             "value": {"en": "Student"},
             "default_price": "10.00",
             "price": "10.00",
             "active": true,
             "description": null,
             "position": 0
          },
          {
             "value": {"en": "Regular"},
             "default_price": null,
             "price": "23.00",
             "active": true,
             "description": null,
             "position": 1
          }
        ],
        "addons": []
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the item to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/items/

   Creates a new item

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/items/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content: application/json

      {
        "id": 1,
        "name": {"en": "Standard ticket"},
        "internal_name": "",
        "sales_channels": ["web"],
        "default_price": "23.00",
        "original_price": null,
        "category": null,
        "active": true,
        "description": null,
        "free_price": false,
        "tax_rate": "0.00",
        "tax_rule": 1,
        "admission": false,
        "position": 0,
        "picture": null,
        "available_from": null,
        "available_until": null,
        "require_voucher": false,
        "hide_without_voucher": false,
        "allow_cancel": true,
        "generate_tickets": null,
        "min_per_order": null,
        "max_per_order": null,
        "checkin_attention": false,
        "require_approval": false,
        "variations": [
          {
             "value": {"en": "Student"},
             "default_price": "10.00",
             "price": "10.00",
             "active": true,
             "description": null,
             "position": 0
          },
          {
             "value": {"en": "Regular"},
             "default_price": null,
             "price": "23.00",
             "active": true,
             "description": null,
             "position": 1
          }
        ],
        "addons": []
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "name": {"en": "Standard ticket"},
        "internal_name": "",
        "sales_channels": ["web"],
        "default_price": "23.00",
        "original_price": null,
        "category": null,
        "active": true,
        "description": null,
        "free_price": false,
        "tax_rate": "0.00",
        "tax_rule": 1,
        "admission": false,
        "position": 0,
        "picture": null,
        "available_from": null,
        "available_until": null,
        "require_voucher": false,
        "hide_without_voucher": false,
        "allow_cancel": true,
        "min_per_order": null,
        "max_per_order": null,
        "generate_tickets": null,
        "checkin_attention": false,
        "has_variations": true,
        "require_approval": false,
        "variations": [
          {
             "value": {"en": "Student"},
             "default_price": "10.00",
             "price": "10.00",
             "active": true,
             "description": null,
             "position": 0
          },
          {
             "value": {"en": "Regular"},
             "default_price": null,
             "price": "23.00",
             "active": true,
             "description": null,
             "position": 1
          }
        ],
        "addons": []
      }

   :param organizer: The ``slug`` field of the organizer of the event to create an item for
   :param event: The ``slug`` field of the event to create an item for
   :statuscode 201: no error
   :statuscode 400: The item could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/items/(id)/

   Update an item. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   You can change all fields of the resource except the ``has_variations``, ``variations`` and the ``addon`` field. If
   you need to update/delete variations or add-ons please use the nested dedicated endpoints.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/items/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "name": {"en": "Ticket"},
        "default_price": "25.00"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "name": {"en": "Ticket"},
        "internal_name": "",
        "sales_channels": ["web"],
        "default_price": "25.00",
        "original_price": null,
        "category": null,
        "active": true,
        "description": null,
        "free_price": false,
        "tax_rate": "0.00",
        "tax_rule": 1,
        "admission": false,
        "position": 0,
        "picture": null,
        "available_from": null,
        "available_until": null,
        "require_voucher": false,
        "hide_without_voucher": false,
        "generate_tickets": null,
        "allow_cancel": true,
        "min_per_order": null,
        "max_per_order": null,
        "checkin_attention": false,
        "has_variations": true,
        "require_approval": false,
        "variations": [
          {
             "value": {"en": "Student"},
             "default_price": "10.00",
             "price": "10.00",
             "active": true,
             "description": null,
             "position": 0
          },
          {
             "value": {"en": "Regular"},
             "default_price": null,
             "price": "23.00",
             "active": true,
             "description": null,
             "position": 1
          }
        ],
        "addons": []
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the item to modify
   :statuscode 200: no error
   :statuscode 400: The item could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to change this resource.

.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/items/(id)/

   Delete an item.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/items/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the item to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to delete this resource.

