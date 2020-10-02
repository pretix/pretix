.. _`rest-giftcards`:

Gift cards
==========

Resource description
--------------------

The gift card resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the gift card
secret                                string                     Gift card code (can not be modified later)
value                                 money (string)             Current gift card value
currency                              string                     Currency of the value (can not be modified later)
testmode                              boolean                    Whether this is a test gift card
expires                               datetime                   Expiry date (or ``null``)
conditions                            string                     Special terms and conditions for this card (or ``null``)
===================================== ========================== =======================================================

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/giftcards/

   Returns a list of all gift cards issued by a given organizer.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/giftcards/ HTTP/1.1
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
            "secret": "HLBYVELFRC77NCQY",
            "currency": "EUR",
            "testmode": false,
            "expires": null,
            "conditions": null,
            "value": "13.37"
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query string secret: Only show gift cards with the given secret.
   :query boolean testmode: Filter for gift cards that are (not) in test mode.
   :query boolean include_accepted: Also show gift cards issued by other organizers that are accepted by this organizer.
   :param organizer: The ``slug`` field of the organizer to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/giftcards/(id)/

   Returns information on one gift card, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/giftcards/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "secret": "HLBYVELFRC77NCQY",
        "currency": "EUR",
        "testmode": false,
        "expires": null,
        "conditions": null,
        "value": "13.37"
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param id: The ``id`` field of the gift card to fetch
   :query boolean include_accepted: Also show gift cards issued by other organizers that are accepted by this organizer.
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/giftcards/

   Creates a new gift card

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/giftcards/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "secret": "HLBYVELFRC77NCQY",
        "currency": "EUR",
        "value": "13.37"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "secret": "HLBYVELFRC77NCQY",
        "testmode": false,
        "currency": "EUR",
        "expires": null,
        "conditions": null,
        "value": "13.37"
      }

   :param organizer: The ``slug`` field of the organizer to create a gift card for
   :statuscode 201: no error
   :statuscode 400: The gift card could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/giftcards/(id)/

   Update a gift card. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   You can change all fields of the resource except the ``id``, ``secret``, ``testmode``, and ``currency`` fields. Be
   careful when modifying the ``value`` field to avoid race conditions. We recommend to use the ``transact`` method
   described below.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/giftcards/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "value": "14.00"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "secret": "HLBYVELFRC77NCQY",
        "testmode": false,
        "currency": "EUR",
        "expires": null,
        "conditions": null,
        "value": "14.00"
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param id: The ``id`` field of the gift card to modify
   :statuscode 200: no error
   :statuscode 400: The gift card could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to change this resource.

.. http:post:: /api/v1/organizers/(organizer)/giftcards/(id)/transact/

   Atomically change the value of a gift card. A positive amount will increase the value of the gift card,
   a negative amount will decrease it.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/giftcards/1/transact/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 79

      {
        "value": "2.00",
        "text": "Optional value explaining the transaction"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "secret": "HLBYVELFRC77NCQY",
        "currency": "EUR",
        "testmode": false,
        "expires": null,
        "conditions": null,
        "value": "15.37"
      }

   .. versionchanged:: 3.5

      This endpoint now returns status code ``409`` if the transaction would lead to a negative gift card value.

   :param organizer: The ``slug`` field of the organizer to modify
   :param id: The ``id`` field of the gift card to modify
   :query boolean include_accepted: Also show gift cards issued by other organizers that are accepted by this organizer.
   :statuscode 200: no error
   :statuscode 400: The gift card could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to change this resource.
   :statuscode 409: There is not sufficient credit on the gift card.
