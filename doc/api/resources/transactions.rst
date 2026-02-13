.. _rest-transactions:

Transactions
============

Transactions are an additional way to think about orders. They are are an immutable, filterable view into an order's
history and are a good basis for financial reporting.

Our financial model
-------------------

You can think of a pretix order similar to a debtor account in double-entry bookkeeping. For example, the flow of an
order could look like this:

===================================================== ==================== =====================
Transaction                                           Debit                Credit
===================================================== ==================== =====================
Order is placed with two tickets                      € 500
Order is paid partially with a gift card                                   € 200
Remainder is paid with a credit card                                       € 300
One of the tickets is canceled                        **-** € 250
Refund is made to the credit card                                          **-** € 250
**Balance**                                           **€ 250**            **€ 250**
===================================================== ==================== =====================

If an order is fully settled, the sums of both columns match. However, as the movements in both columns do not always
happen at the same time, at some times during the lifecycle of an order the sums are not balanced, in which case we
consider an order to be "pending payment" or "overpaid".

In the API, the "Debit" column is represented by the "transaction" resource listed on this page.
In many cases, the left column *usually* also matches the data returned by the :ref:`rest-invoices` resource, but there
are two important differences:

- pretix may be configured such that an invoice is not always generated for an order. In this case, only the transactions
  return the full data set.

- pretix does not enforce a new invoice to be created e.g. when a ticket is changed to a different subevent. However,
  pretix always creates a new transaction whenever there is a change to a ticket that concerns the **price**, **tax rate**,
  **product**, or **date** (in an event series).

The :ref:`rest-orders` themselves are not a good representation of the "Debit" side of the table for accounting
purposes since they are not immutable:
They will only tell you the current state of the order, not what it was a week ago.

The "Credit" column is represented by the :ref:`order-payment-resource` and :ref:`order-refund-resource`.


Resource description
--------------------

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the transaction
order                                 string                     Order code the transaction was created from
event                                 string                     Event slug, only present on organizer-level API calls
created                               datetime                   The creation time of the transaction in the database
datetime                              datetime                   The time at which the transaction is financially relevant.
                                                                 This is usually the same as created, but may vary for
                                                                 retroactively created transactions after software bugs or
                                                                 for data that preceeds this data model.
positionid                            integer                    Number of the position within the order this refers to,
                                                                 is ``null`` for transactions that refer to a fee
count                                 integer                    Number of items purchased, is negative for cancellations
item                                  integer                    The internal ID of the item purchased (or ``null`` for fees)
variation                             integer                    The internal ID of the variation purchased (or ``null``)
subevent                              integer                    The internal ID of the event series date (or ``null``)
price                                 money (string)             Gross price of the transaction
tax_rate                              decimal (string)           Tax rate applied in transaction
tax_rule                              integer                    The internal ID of the tax rule used (or ``null``)
tax_code                              string                     The selected tax code (or ``null``)
tax_value                             money (string)             The computed tax value
fee_type                              string                     The type of fee (or ``null`` for products)
internal_type                         string                     Additional type classification of the fee (or ``null`` for products)
===================================== ========================== =======================================================

.. versionchanged:: 2025.7.0

   This resource was added to the API.


Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/transactions/

   Returns a list of all transactions of an event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/transactions/ HTTP/1.1
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
            "id": 123,
            "order": "FOO",
            "count": 1,
            "created": "2017-12-01T10:00:00Z",
            "datetime": "2017-12-01T10:00:00Z",
            "item": null,
            "variation": null,
            "positionid": 1,
            "price": "23.00",
            "subevent": null,
            "tax_code": "E",
            "tax_rate": "0.00",
            "tax_rule": 23,
            "tax_value": "0.00",
            "fee_type": null,
            "internal_type": null
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query string order: Only return transactions matching the given order code.
   :query datetime_since: Only return transactions with a datetime at or after the given time.
   :query datetime_before: Only return transactions with a datetime before the given time.
   :query created_since: Only return transactions with a creation time at or after the given time.
   :query created_before: Only return transactions with a creation time before the given time.
   :query item: Only return transactions that match the given item ID.
   :query item__in: Only return transactions that match one of the given item IDs (separated with a comma).
   :query variation: Only return transactions that match the given variation ID.
   :query variation__in: Only return transactions that match one of the given variation IDs (separated with a comma).
   :query subevent: Only return transactions that match the given subevent ID.
   :query subevent__in: Only return transactions that match one of the given subevent IDs (separated with a comma).
   :query tax_rule: Only return transactions that match the given tax rule ID.
   :query tax_rule__in: Only return transactions that match one of the given tax rule IDs (separated with a comma).
   :query tax_code: Only return transactions that match the given tax code.
   :query tax_code__in: Only return transactions that match one of the given tax codes (separated with a comma).
   :query tax_rate: Only return transactions that match the given tax rate.
   :query tax_rate__in: Only return transactions that match one of the given tax rates (separated with a comma).
   :query fee_type: Only return transactions that match the given fee type.
   :query fee_type__in: Only return transactions that match one of the given fee types (separated with a comma).
   :query string ordering: Manually set the ordering of results. Valid fields to be used are ``datetime``, ``created``, and ``id``.
   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of a valid event
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or event does not exist **or** you have no permission to view it.

.. http:get:: /api/v1/organizers/(organizer)/transactions/

   Returns a list of all transactions of an organizer that you have access to.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/transactions/ HTTP/1.1
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
            "id": 123,
            "event": "sampleconf",
            "order": "FOO",
            "count": 1,
            "created": "2017-12-01T10:00:00Z",
            "datetime": "2017-12-01T10:00:00Z",
            "item": null,
            "variation": null,
            "positionid": 1,
            "price": "23.00",
            "subevent": null,
            "tax_code": "E",
            "tax_rate": "0.00",
            "tax_rule": 23,
            "tax_value": "0.00",
            "fee_type": null,
            "internal_type": null
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query string event: Only return transactions matching the given event slug.
   :query string order: Only return transactions matching the given order code.
   :query datetime_since: Only return transactions with a datetime at or after the given time.
   :query datetime_before: Only return transactions with a datetime before the given time.
   :query created_since: Only return transactions with a creation time at or after the given time.
   :query created_before: Only return transactions with a creation time before the given time.
   :query item: Only return transactions that match the given item ID.
   :query item__in: Only return transactions that match one of the given item IDs (separated with a comma).
   :query variation: Only return transactions that match the given variation ID.
   :query variation__in: Only return transactions that match one of the given variation IDs (separated with a comma).
   :query subevent: Only return transactions that match the given subevent ID.
   :query subevent__in: Only return transactions that match one of the given subevent IDs (separated with a comma).
   :query tax_rule: Only return transactions that match the given tax rule ID.
   :query tax_rule__in: Only return transactions that match one of the given tax rule IDs (separated with a comma).
   :query tax_code: Only return transactions that match the given tax code.
   :query tax_code__in: Only return transactions that match one of the given tax codes (separated with a comma).
   :query tax_rate: Only return transactions that match the given tax rate.
   :query tax_rate__in: Only return transactions that match one of the given tax rates (separated with a comma).
   :query fee_type: Only return transactions that match the given fee type.
   :query fee_type__in: Only return transactions that match one of the given fee types (separated with a comma).
   :query string ordering: Manually set the ordering of results. Valid fields to be used are ``datetime``, ``created``, and ``id``.
   :param organizer: The ``slug`` field of a valid organizer
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.
