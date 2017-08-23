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
has_variations                        boolean                    Shows whether or not this item has variations
                                                                 (read-only).
variations                            list of objects            A list with one object for each variation of this item.
                                                                 Can be empty.
├ id                                  integer                    Internal ID of the variation
├ default_price                       money (string)             The price set directly for this variation or ``null``
├ price                               money (string)             The price used for this variation. This is either the
                                                                 same as ``default_price`` if that value is set or equal
                                                                 to the item's ``default_price``.
├ active                              boolean                    If ``False``, this variation will not be sold or shown.
├ description                         multi-lingual string       A public description of the variation. May contain
                                                                 Markdown syntax or can be ``null``.
└ position                            integer                    An integer, used for sorting
addons                                list of objects            Definition of add-ons that can be chosen for this item
├ addon_category                      integer                    Internal ID of the item category the add-on can be
                                                                 chosen from.
├ min_count                           integer                    The minimal number of add-ons that need to be chosen.
├ max_count                           integer                    The maxima number of add-ons that can be chosen.
└ position                            integer                    An integer, used for sorting
===================================== ========================== =======================================================

.. versionchanged:: 1.7

   The attribute ``tax_rule`` has been added. ``tax_rate`` is kept for compatibility.


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
      Content-Type: text/javascript

      {
        "count": 1,
        "next": null,
        "previous": null,
        "results": [
          {
            "id": 1,
            "name": {"en": "Standard ticket"},
            "default_price": "23.00",
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
            "has_variations": false,
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
      Content-Type: text/javascript

      {
        "id": 1,
        "name": {"en": "Standard ticket"},
        "default_price": "23.00",
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
        "has_variations": false,
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
