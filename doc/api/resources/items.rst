.. _rest-items:

Items
=====

Resource description
--------------------

Items (better known as products) are the things that can be sold using pretix.
The item resource contains the following public fields:

.. rst-class:: rest-resource-table

======================================= ========================== =======================================================
Field                                   Type                       Description
======================================= ========================== =======================================================
id                                      integer                    Internal ID of the item
name                                    multi-lingual string       The item's visible name
internal_name                           string                     An optional name that is only used in the backend
default_price                           money (string)             The item price that is applied if the price is not
                                                                   overwritten by variations or other options.
category                                integer                    The ID of the category this item belongs to
                                                                   (or ``null``).
active                                  boolean                    If ``false``, the item is hidden from all public lists
                                                                   and will not be sold.
description                             multi-lingual string       A public description of the item. May contain Markdown
                                                                   syntax or can be ``null``.
free_price                              boolean                    If ``true``, customers can change the price at which
                                                                   they buy the product (however, the price can't be set
                                                                   lower than the price defined by ``default_price`` or
                                                                   otherwise).
free_price_suggestion                   money (string)             A suggested price, used as a default value if
                                                                   ``free_price`` is set (or ``null``).
tax_rate                                decimal (string)           The VAT rate to be applied for this item (read-only,
                                                                   set through ``tax_rule``).
tax_rule                                integer                    The internal ID of the applied tax rule (or ``null``).
admission                               boolean                    ``true`` for items that grant admission to the event
                                                                   (such as primary tickets) and ``false`` for others
                                                                   (such as add-ons or merchandise).
personalized                            boolean                    ``true`` for items that require personalization according
                                                                   to event settings. Only affects system-level fields, not
                                                                   custom questions. Currently only allowed for products with
                                                                   ``admission`` set to ``true``. For backwards compatibility,
                                                                   when creating new items and this field is not given, it defaults
                                                                   to the same value as ``admission``.
position                                integer                    An integer, used for sorting
picture                                 file                       A product picture to be displayed in the shop
                                                                   (can be ``null``).
sales_channels                          list of strings            Sales channels this product is available on, such as
                                                                   ``"web"`` or ``"resellers"``. Defaults to ``["web"]``.
available_from                          datetime                   The first date time at which this item can be bought
                                                                   (or ``null``).
available_until                         datetime                   The last date time at which this item can be bought
                                                                   (or ``null``).
hidden_if_available                     integer                    **DEPRECATED** The internal ID of a quota object, or ``null``. If
                                                                   set, this item won't be shown publicly as long as this
                                                                   quota is available.
hidden_if_item_available                integer                    The internal ID of a different item, or ``null``. If
                                                                   set, this item won't be shown publicly as long as this
                                                                   other item is available.
require_voucher                         boolean                    If ``true``, this item can only be bought using a
                                                                   voucher that is specifically assigned to this item.
hide_without_voucher                    boolean                    If ``true``, this item is only shown during the voucher
                                                                   redemption process, but not in the normal shop
                                                                   frontend.
allow_cancel                            boolean                    If ``false``, customers cannot cancel orders containing
                                                                   this item.
min_per_order                           integer                    This product can only be bought if it is included at
                                                                   least this many times in the order (or ``null`` for no
                                                                   limitation).
max_per_order                           integer                    This product can only be bought if it is included at
                                                                   most this many times in the order (or ``null`` for no
                                                                   limitation).
checkin_attention                       boolean                    If ``true``, the check-in app should show a warning
                                                                   that this ticket requires special attention if such
                                                                   a product is being scanned.
checkin_text                            string                     Text that will be shown if a ticket of this type is
                                                                   scanned (or ``null``).
original_price                          money (string)             An original price, shown for comparison, not used
                                                                   for price calculations (or ``null``).
require_approval                        boolean                    If ``true``, orders with this product will need to be
                                                                   approved by the event organizer before they can be
                                                                   paid.
require_bundling                        boolean                    If ``true``, this item is only available as part of bundles.
require_membership                      boolean                    If ``true``, booking this item requires an active membership.
require_membership_hidden               boolean                    If ``true`` and ``require_membership`` is set, this product will
                                                                   be hidden from users without a valid membership.
require_membership_types                list of integers           Internal IDs of membership types valid if ``require_membership`` is ``true``
grant_membership_type                   integer                    If set to the internal ID of a membership type, purchasing this item will
                                                                   create a membership of the given type.
grant_membership_duration_like_event    boolean                    If ``true``, the membership created through ``grant_membership_type`` will derive
                                                                   its term from ``date_from`` to ``date_to`` of the purchased (sub)event.
grant_membership_duration_days          integer                    If ``grant_membership_duration_like_event`` is ``false``, this sets the number of
                                                                   days for the membership.
grant_membership_duration_months        integer                    If ``grant_membership_duration_like_event`` is ``false``, this sets the number of
                                                                   calendar months for the membership.
validity_mode                           string                     If ``null``, tickets generated for this product do not
                                                                   have special validity behavior, but follow event configuration and
                                                                   can be limited e.g. through check-in rules. Other values are ``"fixed"`` and ``"dynamic"``
validity_fixed_from                     datetime                   If ``validity_mode`` is ``"fixed"``, this is the start of validity for issued tickets.
validity_fixed_until                    datetime                   If ``validity_mode`` is ``"fixed"``, this is the end of validity for issued tickets.
validity_dynamic_duration_minutes       integer                    If ``validity_mode`` is ``"dynamic"``, this is the "minutes" component of the ticket validity duration.
validity_dynamic_duration_hours         integer                    If ``validity_mode`` is ``"dynamic"``, this is the "hours" component of the ticket validity duration.
validity_dynamic_duration_days          integer                    If ``validity_mode`` is ``"dynamic"``, this is the "days" component of the ticket validity duration.
validity_dynamic_duration_months        integer                    If ``validity_mode`` is ``"dynamic"``, this is the "months" component of the ticket validity duration.
validity_dynamic_start_choice           boolean                    If ``validity_mode`` is ``"dynamic"`` and this is ``true``, customers can choose the start of validity.
validity_dynamic_start_choice_day_limit boolean                    If ``validity_mode`` is ``"dynamic"`` and ``validity_dynamic_start_choice`` is ``true``,
                                                                   this is the maximum number of days the start can be in the future.
generate_tickets                        boolean                    If ``false``, tickets are never generated for this
                                                                   product, regardless of other settings. If ``true``,
                                                                   tickets are generated even if this is a
                                                                   non-admission or add-on product, regardless of event
                                                                   settings. If this is ``null``, regular ticketing
                                                                   rules apply.
allow_waitinglist                       boolean                    If ``false``, no waiting list will be shown for this
                                                                   product when it is sold out.
issue_giftcard                          boolean                    If ``true``, buying this product will yield a gift card.
media_policy                            string                     Policy on how to handle reusable media (experimental feature).
                                                                   Possible values are ``null``, ``"new"``, ``"reuse"``, and ``"reuse_or_new"``.
media_type                              string                     Type of reusable media to work on (experimental feature). See :ref:`rest-reusablemedia` for possible choices.
show_quota_left                         boolean                    Publicly show how many tickets are still available.
                                                                   If this is ``null``, the event default is used.
has_variations                          boolean                    Shows whether or not this item has variations.
variations                              list of objects            A list with one object for each variation of this item.
                                                                   Can be empty. Only writable during creation,
                                                                   use separate endpoint to modify this later.
├ id                                    integer                    Internal ID of the variation
├ value                                 multi-lingual string       The "name" of the variation
├ default_price                         money (string)             The price set directly for this variation or ``null``
├ price                                 money (string)             The price used for this variation. This is either the
                                                                   same as ``default_price`` if that value is set or equal
                                                                   to the item's ``default_price``.
├ free_price_suggestion                 money (string)             A suggested price, used as a default value if
                                                                   ``free_price`` is set (or ``null``).
├ original_price                        money (string)             An original price, shown for comparison, not used
                                                                   for price calculations (or ``null``).
├ active                                boolean                    If ``false``, this variation will not be sold or shown.
├ description                           multi-lingual string       A public description of the variation. May contain
├ checkin_attention                     boolean                    If ``true``, the check-in app should show a warning
                                                                   that this ticket requires special attention if such
                                                                   a variation is being scanned.
├ checkin_text                          string                     Text that will be shown if a ticket of this type is
                                                                   scanned (or ``null``).
├ require_approval                      boolean                    If ``true``, orders with this variation will need to be
                                                                   approved by the event organizer before they can be
                                                                   paid.
├ require_membership                    boolean                    If ``true``, booking this variation requires an active membership.
├ require_membership_hidden             boolean                    If ``true`` and ``require_membership`` is set, this variation will
                                                                   be hidden from users without a valid membership.
├ require_membership_types              list of integers           Internal IDs of membership types valid if ``require_membership`` is ``true``
                                                                   Markdown syntax or can be ``null``.
├ sales_channels                        list of strings            Sales channels this variation is available on, such as
                                                                   ``"web"`` or ``"resellers"``. Defaults to all existing sales channels.
                                                                   The item-level list takes precedence, i.e. a sales
                                                                   channel needs to be on both lists for the item to be
                                                                   available.
├ available_from                        datetime                   The first date time at which this variation can be bought
                                                                   (or ``null``).
├ available_until                       datetime                   The last date time at which this variation can be bought
                                                                   (or ``null``).
├ hide_without_voucher                  boolean                    If ``true``, this variation is only shown during the voucher
                                                                   redemption process, but not in the normal shop
                                                                   frontend.
├ meta_data                             object                     Values set for event-specific meta data parameters.
└ position                              integer                    An integer, used for sorting
addons                                  list of objects            Definition of add-ons that can be chosen for this item.
                                                                   Only writable during creation,
                                                                   use separate endpoint to modify this later.
├ addon_category                        integer                    Internal ID of the item category the add-on can be
                                                                   chosen from.
├ min_count                             integer                    The minimal number of add-ons that need to be chosen.
├ max_count                             integer                    The maximal number of add-ons that can be chosen.
├ position                              integer                    An integer, used for sorting
├ multi_allowed                         boolean                    Adding the same item multiple times is allowed
└ price_included                        boolean                    Adding this add-on to the item is free
bundles                                 list of objects            Definition of bundles that are included in this item.
                                                                   Only writable during creation,
                                                                   use separate endpoint to modify this later.
├ bundled_item                          integer                    Internal ID of the item that is included.
├ bundled_variation                     integer                    Internal ID of the variation of the item (or ``null``).
├ count                                 integer                    Number of items included
└ designated_price                      money (string)             Designated price of the bundled product. This will be
                                                                   used to split the price of the base item e.g. for mixed
                                                                   taxation. This is not added to the price.
meta_data                               object                     Values set for event-specific meta data parameters.
======================================= ========================== =======================================================

.. versionchanged:: 4.0

   The attributes ``require_membership``, ``require_membership_types``, ``grant_membership_type``, ``grant_membership_duration_like_event``,
    ``grant_membership_duration_days`` and ``grant_membership_duration_months`` have been added.

.. versionchanged:: 4.4

   The attributes ``require_membership_hidden`` attribute has been added.

.. versionchanged:: 4.16

   The ``variations[x].meta_data`` and ``variations[x].checkin_attention`` attributes have been added.
   The ``personalized`` attribute has been added.

.. versionchanged:: 4.17

   The ``validity_*`` attributes have been added.

.. versionchanged:: 4.18

   The ``media_policy`` and ``media_type`` attributes have been added.

.. versionchanged:: 2023.10

   The ``free_price_suggestion`` and ``variations[x].free_price_suggestion`` attributes have been added.

.. versionchanged:: 2023.10

   The ``hidden_if_item_available`` attributes has been added, the ``hidden_if_available`` attribute has been
   deprecated.

Notes
-----

Please note that an item either always has variations or never has. Once created with variations the item can never
change to an item without and vice versa. To create an item with variations ensure that you POST an item with at least
one variation.

Also note that ``variations``, ``bundles``, and  ``addons`` are only supported on ``POST``. To update/delete variations,
bundles, and add-ons please use the dedicated nested endpoints. By design this endpoint does not support ``PATCH`` and ``PUT``
with nested ``variations``, ``bundles`` and/or ``addons``.

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
            "free_price_suggestion": null,
            "tax_rate": "0.00",
            "tax_rule": 1,
            "admission": false,
            "personalized": false,
            "issue_giftcard": false,
            "media_policy": null,
            "media_type": null,
            "meta_data": {},
            "position": 0,
            "picture": null,
            "available_from": null,
            "available_until": null,
            "hidden_if_available": null,
            "hidden_if_item_available": null,
            "require_voucher": false,
            "hide_without_voucher": false,
            "allow_cancel": true,
            "min_per_order": null,
            "max_per_order": null,
            "checkin_attention": false,
            "checkin_text": null,
            "has_variations": false,
            "generate_tickets": null,
            "allow_waitinglist": true,
            "show_quota_left": null,
            "require_approval": false,
            "require_bundling": false,
            "require_membership": false,
            "require_membership_types": [],
            "grant_membership_type": null,
            "grant_membership_duration_like_event": true,
            "grant_membership_duration_days": 0,
            "grant_membership_duration_months": 0,
            "validity_fixed_from": null,
            "validity_fixed_until": null,
            "validity_dynamic_duration_minutes": null,
            "validity_dynamic_duration_hours": null,
            "validity_dynamic_duration_days": null,
            "validity_dynamic_duration_months": null,
            "validity_dynamic_start_choice": false,
            "validity_dynamic_start_choice_day_limit": null,
            "variations": [
              {
                 "value": {"en": "Student"},
                 "default_price": "10.00",
                 "price": "10.00",
                 "original_price": null,
                 "free_price_suggestion": null,
                 "active": true,
                 "checkin_attention": false,
                 "checkin_text": null,
                 "require_approval": false,
                 "require_membership": false,
                 "require_membership_types": [],
                 "sales_channels": ["web"],
                 "available_from": null,
                 "available_until": null,
                 "hide_without_voucher": false,
                 "description": null,
                 "meta_data": {},
                 "position": 0
              },
              {
                 "value": {"en": "Regular"},
                 "default_price": null,
                 "price": "23.00",
                 "original_price": null,
                 "free_price_suggestion": null,
                 "active": true,
                 "checkin_attention": false,
                 "checkin_text": null,
                 "require_approval": false,
                 "require_membership": false,
                 "require_membership_types": [],
                 "sales_channels": ["web"],
                 "available_from": null,
                 "available_until": null,
                 "hide_without_voucher": false,
                 "description": null,
                 "meta_data": {},
                 "position": 1
              }
            ],
            "addons": [],
            "bundles": []
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
        "free_price_suggestion": null,
        "tax_rate": "0.00",
        "tax_rule": 1,
        "admission": false,
        "personalized": false,
        "issue_giftcard": false,
        "media_policy": null,
        "media_type": null,
        "meta_data": {},
        "position": 0,
        "picture": null,
        "available_from": null,
        "available_until": null,
        "hidden_if_available": null,
        "hidden_if_item_available": null,
        "require_voucher": false,
        "hide_without_voucher": false,
        "allow_cancel": true,
        "generate_tickets": null,
        "allow_waitinglist": true,
        "show_quota_left": null,
        "min_per_order": null,
        "max_per_order": null,
        "checkin_attention": false,
        "checkin_text": null,
        "has_variations": false,
        "require_approval": false,
        "require_bundling": false,
        "require_membership": false,
        "require_membership_types": [],
        "grant_membership_type": null,
        "grant_membership_duration_like_event": true,
        "grant_membership_duration_days": 0,
        "grant_membership_duration_months": 0,
        "validity_fixed_from": null,
        "validity_fixed_until": null,
        "validity_dynamic_duration_minutes": null,
        "validity_dynamic_duration_hours": null,
        "validity_dynamic_duration_days": null,
        "validity_dynamic_duration_months": null,
        "validity_dynamic_start_choice": false,
        "validity_dynamic_start_choice_day_limit": null,
        "variations": [
          {
             "value": {"en": "Student"},
             "default_price": "10.00",
             "price": "10.00",
             "original_price": null,
             "free_price_suggestion": null,
             "active": true,
             "checkin_attention": false,
             "checkin_text": null,
             "require_approval": false,
             "require_membership": false,
             "require_membership_types": [],
             "description": null,
             "sales_channels": ["web"],
             "available_from": null,
             "available_until": null,
             "hide_without_voucher": false,
             "meta_data": {},
             "position": 0
          },
          {
             "value": {"en": "Regular"},
             "default_price": null,
             "price": "23.00",
             "original_price": null,
             "free_price_suggestion": null,
             "active": true,
             "checkin_attention": false,
             "checkin_text": null,
             "require_approval": false,
             "require_membership": false,
             "require_membership_types": [],
             "sales_channels": ["web"],
             "available_from": null,
             "available_until": null,
             "hide_without_voucher": false,
             "description": null,
             "meta_data": {},
             "position": 1
          }
        ],
        "addons": [],
        "bundles": []
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
        "free_price_suggestion": null,
        "tax_rate": "0.00",
        "tax_rule": 1,
        "admission": false,
        "personalized": false,
        "issue_giftcard": false,
        "media_policy": null,
        "media_type": null,
        "meta_data": {},
        "position": 0,
        "picture": null,
        "available_from": null,
        "available_until": null,
        "hidden_if_available": null,
        "hidden_if_item_available": null,
        "require_voucher": false,
        "hide_without_voucher": false,
        "allow_cancel": true,
        "generate_tickets": null,
        "allow_waitinglist": true,
        "show_quota_left": null,
        "min_per_order": null,
        "max_per_order": null,
        "checkin_attention": false,
        "checkin_text": null,
        "require_approval": false,
        "require_bundling": false,
        "require_membership": false,
        "require_membership_types": [],
        "grant_membership_type": null,
        "grant_membership_duration_like_event": true,
        "grant_membership_duration_days": 0,
        "grant_membership_duration_months": 0,
        "validity_fixed_from": null,
        "validity_fixed_until": null,
        "validity_dynamic_duration_minutes": null,
        "validity_dynamic_duration_hours": null,
        "validity_dynamic_duration_days": null,
        "validity_dynamic_duration_months": null,
        "validity_dynamic_start_choice": false,
        "validity_dynamic_start_choice_day_limit": null,
        "variations": [
          {
             "value": {"en": "Student"},
             "default_price": "10.00",
             "price": "10.00",
             "original_price": null,
             "free_price_suggestion": null,
             "active": true,
             "checkin_attention": false,
             "checkin_text": null,
             "require_approval": false,
             "require_membership": false,
             "require_membership_types": [],
             "sales_channels": ["web"],
             "available_from": null,
             "available_until": null,
             "hide_without_voucher": false,
             "description": null,
             "meta_data": {},
             "position": 0
          },
          {
             "value": {"en": "Regular"},
             "default_price": null,
             "price": "23.00",
             "original_price": null,
             "free_price_suggestion": null,
             "active": true,
             "checkin_attention": false,
             "checkin_text": null,
             "require_approval": false,
             "require_membership": false,
             "require_membership_types": [],
             "sales_channels": ["web"],
             "available_from": null,
             "available_until": null,
             "hide_without_voucher": false,
             "description": null,
             "meta_data": {},
             "position": 1
          }
        ],
        "addons": [],
        "bundles": []
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
        "free_price_suggestion": null,
        "tax_rate": "0.00",
        "tax_rule": 1,
        "admission": false,
        "personalized": false,
        "issue_giftcard": false,
        "media_policy": null,
        "media_type": null,
        "meta_data": {},
        "position": 0,
        "picture": null,
        "available_from": null,
        "available_until": null,
        "hidden_if_available": null,
        "hidden_if_item_available": null,
        "require_voucher": false,
        "hide_without_voucher": false,
        "allow_cancel": true,
        "min_per_order": null,
        "max_per_order": null,
        "generate_tickets": null,
        "allow_waitinglist": true,
        "show_quota_left": null,
        "checkin_attention": false,
        "checkin_text": null,
        "has_variations": true,
        "require_approval": false,
        "require_bundling": false,
        "require_membership": false,
        "require_membership_types": [],
        "grant_membership_type": null,
        "grant_membership_duration_like_event": true,
        "grant_membership_duration_days": 0,
        "grant_membership_duration_months": 0,
        "validity_fixed_from": null,
        "validity_fixed_until": null,
        "validity_dynamic_duration_minutes": null,
        "validity_dynamic_duration_hours": null,
        "validity_dynamic_duration_days": null,
        "validity_dynamic_duration_months": null,
        "validity_dynamic_start_choice": false,
        "validity_dynamic_start_choice_day_limit": null,
        "variations": [
          {
             "value": {"en": "Student"},
             "default_price": "10.00",
             "price": "10.00",
             "original_price": null,
             "free_price_suggestion": null,
             "active": true,
             "checkin_attention": false,
             "checkin_text": null,
             "require_approval": false,
             "require_membership": false,
             "require_membership_types": [],
             "sales_channels": ["web"],
             "available_from": null,
             "available_until": null,
             "hide_without_voucher": false,
             "description": null,
             "meta_data": {},
             "position": 0
          },
          {
             "value": {"en": "Regular"},
             "default_price": null,
             "price": "23.00",
             "original_price": null,
             "free_price_suggestion": null,
             "active": true,
             "checkin_attention": false,
             "checkin_text": null,
             "require_approval": false,
             "require_membership": false,
             "require_membership_types": [],
             "sales_channels": ["web"],
             "available_from": null,
             "available_until": null,
             "hide_without_voucher": false,
             "description": null,
             "meta_data": {},
             "position": 1
          }
        ],
        "addons": [],
        "bundles": []
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
        "free_price_suggestion": null,
        "tax_rate": "0.00",
        "tax_rule": 1,
        "admission": false,
        "personalized": false,
        "issue_giftcard": false,
        "media_policy": null,
        "media_type": null,
        "meta_data": {},
        "position": 0,
        "picture": null,
        "available_from": null,
        "available_until": null,
        "hidden_if_available": null,
        "hidden_if_item_available": null,
        "require_voucher": false,
        "hide_without_voucher": false,
        "generate_tickets": null,
        "allow_waitinglist": true,
        "show_quota_left": null,
        "allow_cancel": true,
        "min_per_order": null,
        "max_per_order": null,
        "checkin_attention": false,
        "checkin_text": null,
        "has_variations": true,
        "require_approval": false,
        "require_bundling": false,
        "require_membership": false,
        "require_membership_types": [],
        "grant_membership_type": null,
        "grant_membership_duration_like_event": true,
        "grant_membership_duration_days": 0,
        "grant_membership_duration_months": 0,
        "validity_fixed_from": null,
        "validity_fixed_until": null,
        "validity_dynamic_duration_minutes": null,
        "validity_dynamic_duration_hours": null,
        "validity_dynamic_duration_days": null,
        "validity_dynamic_duration_months": null,
        "validity_dynamic_start_choice": false,
        "validity_dynamic_start_choice_day_limit": null,
        "variations": [
          {
             "value": {"en": "Student"},
             "default_price": "10.00",
             "price": "10.00",
             "original_price": null,
             "free_price_suggestion": null,
             "active": true,
             "checkin_attention": false,
             "checkin_text": null,
             "require_approval": false,
             "require_membership": false,
             "require_membership_types": [],
             "sales_channels": ["web"],
             "available_from": null,
             "available_until": null,
             "hide_without_voucher": false,
             "description": null,
             "meta_data": {},
             "position": 0
          },
          {
             "value": {"en": "Regular"},
             "default_price": null,
             "price": "23.00",
             "original_price": null,
             "free_price_suggestion": null,
             "active": true,
             "checkin_attention": false,
             "checkin_text": null,
             "require_approval": false,
             "require_membership": false,
             "require_membership_types": [],
             "sales_channels": ["web"],
             "available_from": null,
             "available_until": null,
             "hide_without_voucher": false,
             "description": null,
             "meta_data": {},
             "position": 1
          }
        ],
        "addons": [],
        "bundles": []
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

