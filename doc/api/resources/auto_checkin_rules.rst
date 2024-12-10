.. _rest-autocheckinrules:

Auto check-in rules
===================

This feature requires the bundled ``pretix.plugins.autocheckin`` plugin to be active for the event in order to work properly.

Resource description
--------------------

Auto check-in rules specify that tickets should under specific conditions automatically be considered checked in after
they have been purchased.

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the rule
list                                  integer                    ID of the check-in list to check the ticket in on. If
                                                                 ``None``, the system will select all matching check-in lists.
mode                                  string                     ``"placed"`` if the rule should be evaluated right after
                                                                 an order has been created, ``"paid"`` if the rule should
                                                                 be evaluated after the order has been fully paid.
all_sales_channels                    boolean                    If ``true`` (default), the rule applies to tickets sold on all sales channels.
limit_sales_channels                  list of strings            List of sales channel identifiers the rule should apply to
                                                                 if ``all_sales_channels`` is ``false``.
all_products                          boolean                    If ``true`` (default), the rule affects all products and variations.
limit_products                        list of integers           List of item IDs, if ``all_products`` is not set. If the
                                                                 product listed here has variations, all variations will be matched.
limit_variations                      list of integers           List of product variation IDs, if ``all_products`` is not set.
                                                                 The parent product does not need to be part of ``limit_products``.
all_payment_methods                   boolean                    If ``true`` (default), the rule applies to tickets paid with all payment methods.
limit_payment_methods                 list of strings            List of payment method identifiers the rule should apply to
                                                                 if ``all_payment_methods`` is ``false``.
===================================== ========================== =======================================================

.. versionadded:: 2024.7

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/auto_checkin_rules/

   Returns a list of all rules configured for an event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/auto_checkin_rules/ HTTP/1.1
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
            "list": 12345,
            "mode": "placed",
            "all_sales_channels": false,
            "limit_sales_channels": ["web"],
            "all_products": false,
            "limit_products": [2, 3],
            "limit_variations": [456],
            "all_payment_methods": true,
            "limit_payment_methods": []
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/auto_checkin_rules/(id)/

   Returns information on one rule, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/auto_checkin_rules/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "list": 12345,
        "mode": "placed",
        "all_sales_channels": false,
        "limit_sales_channels": ["web"],
        "all_products": false,
        "limit_products": [2, 3],
        "limit_variations": [456],
        "all_payment_methods": true,
        "limit_payment_methods": []
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the rule to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event/rule does not exist **or** you have no permission to view it.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/auto_checkin_rules/

   Create a new rule.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/auto_checkin_rules/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 166

      {
        "list": 12345,
        "mode": "placed",
        "all_sales_channels": false,
        "limit_sales_channels": ["web"],
        "all_products": false,
        "limit_products": [2, 3],
        "limit_variations": [456],
        "all_payment_methods": true,
        "limit_payment_methods": []
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "list": 12345,
        "mode": "placed",
        "all_sales_channels": false,
        "limit_sales_channels": ["web"],
        "all_products": false,
        "limit_products": [2, 3],
        "limit_variations": [456],
        "all_payment_methods": true,
        "limit_payment_methods": []
      }

   :param organizer: The ``slug`` field of the organizer to create a rule for
   :param event: The ``slug`` field of the event to create a rule for
   :statuscode 201: no error
   :statuscode 400: The rule could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create rules.


.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/auto_checkin_rules/(id)/

   Update a rule. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/auto_checkin_rules/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 34

      {
        "mode": "paid",
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: text/javascript

      {
        "id": 1,
        "list": 12345,
        "mode": "placed",
        "all_sales_channels": false,
        "limit_sales_channels": ["web"],
        "all_products": false,
        "limit_products": [2, 3],
        "limit_variations": [456],
        "all_payment_methods": true,
        "limit_payment_methods": []
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the rule to modify
   :statuscode 200: no error
   :statuscode 400: The rule could not be modified due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event/rule does not exist **or** you have no permission to change it.


.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/auto_checkin_rules/(id)/

   Delete a rule.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/auto_checkin_rules/1/ HTTP/1.1
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
