pretixdroid HTTP API
====================

The pretixdroid plugin provides a HTTP API that the `pretixdroid Android app`_
uses to communicate with the pretix server.

.. warning:: This API is **DEPRECATED** and will probably go away soon. It is used **only** to serve the pretixdroid
             Android app. There are no backwards compatibility guarantees on this API. We will not add features that
             are not required for the  Android App. There is a general-purpose :ref:`rest-api` that provides all
             features that you need to check in.

.. versionchanged:: 1.12

   Support for check-in-time questions has been added. The new API features are fully backwards-compatible and
   negotiated live, so clients which do not need this feature can ignore the change. For this reason, the API version
   has not been increased and is still set to 3.

.. versionchanged:: 1.13

   Support for checking in unpaid tickets has been added.


.. http:post:: /pretixdroid/api/(organizer)/(event)/redeem/

   Redeems a ticket, i.e. checks the user in.

   **Example request**:

   .. sourcecode:: http

      POST /pretixdroid/api/demoorga/democon/redeem/?key=ABCDEF HTTP/1.1
      Host: demo.pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/x-www-form-urlencoded

      secret=az9u4mymhqktrbupmwkvv6xmgds5dk3&questions_supported=true

   You **must** set the parameter secret.

   You **must** set the parameter ``questions_supported`` to ``true`` **if** you support asking questions
   back to the app operator. You **must not** set it if you do not support this feature. In that case, questions
   will just be ignored.

   You **may** set the additional parameter ``datetime`` in the body containing an ISO8601-encoded
   datetime of the entry attempt. If you don"t, the current date and time will be used.

   You **may** set the additional parameter ``force`` to indicate that the request should be logged
   regardless of previous check-ins for the same ticket. This might be useful if you made the entry decision offline.
   Questions will also always be ignored in this case (i.e. supplied answers will be saved, but no error will be
   thrown if they are missing or invalid).

   You **may** set the additional parameter ``nonce`` with a globally unique random value to identify this
   check-in. This is meant to be used to prevent duplicate check-ins when you are just retrying after a connection
   failure.

   You **may** set the additional parameter ``ignore_unpaid`` to indicate that the check-in should be performed even
   if the order is in pending state.

   If questions are supported and required, you will receive a dictionary ``questions`` containing details on the
   particular questions to ask. To answer them, just re-send your redemption request with additional parameters of
   the form ``answer_<question>=<answer>``, e.g. ``answer_12=24``.

   **Example successful response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: text/json

      {
        "status": "ok"
        "version": 3,
        "data": {
          "secret": "az9u4mymhqktrbupmwkvv6xmgds5dk3",
          "order": "ABCDE",
          "item": "Standard ticket",
          "item_id": 1,
          "variation": null,
          "variation_id": null,
          "attendee_name": "Peter Higgs",
          "attention": false,
          "redeemed": true,
          "checkin_allowed": true,
          "addons_text": "Parking spot",
          "paid": true
        }
      }

   **Example response with required questions**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: text/json

      {
        "status": "incomplete"
        "version": 3
        "data": {
          "secret": "az9u4mymhqktrbupmwkvv6xmgds5dk3",
          "order": "ABCDE",
          "item": "Standard ticket",
          "item_id": 1,
          "variation": null,
          "variation_id": null,
          "attendee_name": "Peter Higgs",
          "attention": false,
          "redeemed": true,
          "checkin_allowed": true,
          "addons_text": "Parking spot",
          "paid": true
        },
        "questions": [
          {
            "id": 12,
            "type": "C",
            "question": "Choose a shirt size",
            "required": true,
            "position": 2,
            "items": [1],
            "options": [
              {
                "id": 24,
                "answer": "M"
              },
              {
                "id": 25,
                "answer": "L"
              }
            ]
          }
        ]
      }

   **Example error response with data**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: text/json

      {
        "status": "error",
        "reason": "already_redeemed",
        "version": 3,
        "data": {
          "secret": "az9u4mymhqktrbupmwkvv6xmgds5dk3",
          "order": "ABCDE",
          "item": "Standard ticket",
          "item_id": 1,
          "variation": null,
          "variation_id": null,
          "attendee_name": "Peter Higgs",
          "attention": false,
          "redeemed": true,
          "checkin_allowed": true,
          "addons_text": "Parking spot",
          "paid": true
        }
      }

   **Example error response without data**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: text/json

      {
        "status": "error",
        "reason": "unkown_ticket",
        "version": 3
      }

   Possible error reasons:

   * ``unpaid`` - Ticket is not paid for or has been refunded
   * ``already_redeemed`` - Ticket already has been redeemed
   * ``product`` - Tickets with this product may not be scanned at this device
   * ``unknown_ticket`` - Secret does not match a ticket in the database

   :query key: Secret API key
   :statuscode 200: Valid request
   :statuscode 404: Unknown organizer or event
   :statuscode 403: Invalid authorization key

.. http:get:: /pretixdroid/api/(organizer)/(event)/search/

   Searches for a ticket.
   At most 25 results will be returned. **Queries with less than 4 characters will always return an empty result set.**

   **Example request**:

   .. sourcecode:: http

      GET /pretixdroid/api/demoorga/democon/search/?key=ABCDEF&query=Peter HTTP/1.1
      Host: demo.pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: text/json

      {
        "results": [
          {
            "secret": "az9u4mymhqktrbupmwkvv6xmgds5dk3",
            "order": "ABCE6",
            "item": "Standard ticket",
            "variation": null,
            "attendee_name": "Peter Higgs",
            "redeemed": false,
            "attention": false,
            "checkin_allowed": true,
            "addons_text": "Parking spot",
            "paid": true
          },
          ...
        ],
        "version": 3
      }

   :query query: Search query
   :query key: Secret API key
   :statuscode 200: Valid request
   :statuscode 404: Unknown organizer or event
   :statuscode 403: Invalid authorization key

.. http:get:: /pretixdroid/api/(organizer)/(event)/download/

   Download data for all tickets.

   **Example request**:

   .. sourcecode:: http

      GET /pretixdroid/api/demoorga/democon/download/?key=ABCDEF HTTP/1.1
      Host: demo.pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: text/json

      {
        "version": 3,
        "results": [
          {
            "secret": "az9u4mymhqktrbupmwkvv6xmgds5dk3",
            "order": "ABCE6",
            "item": "Standard ticket",
            "variation": null,
            "attendee_name": "Peter Higgs",
            "redeemed": false,
            "attention": false,
            "checkin_allowed": true,
            "paid": true
          },
          ...
        ],
        "questions": [
          {
            "id": 12,
            "type": "C",
            "question": "Choose a shirt size",
            "required": true,
            "position": 2,
            "items": [1],
            "options": [
              {
                "id": 24,
                "answer": "M"
              },
              {
                "id": 25,
                "answer": "L"
              }
            ]
          }
        ]
      }

   :query key: Secret API key
   :statuscode 200: Valid request
   :statuscode 404: Unknown organizer or event
   :statuscode 403: Invalid authorization key

.. http:get:: /pretixdroid/api/(organizer)/(event)/status/

   Returns status information, such as the total number of tickets and the
   number of performed check-ins.

   **Example request**:

   .. sourcecode:: http

      GET /pretixdroid/api/demoorga/democon/status/?key=ABCDEF HTTP/1.1
      Host: demo.pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: text/json

      {
        "checkins": 17,
        "total": 42,
        "version": 3,
        "event": {
          "name": "Demo Conference",
          "slug": "democon",
          "date_from": "2016-12-27T17:00:00Z",
          "date_to": "2016-12-30T18:00:00Z",
          "timezone": "UTC",
          "url": "https://demo.pretix.eu/demoorga/democon/",
          "organizer": {
            "name": "Demo Organizer",
            "slug": "demoorga"
          },
        },
        "items": [
          {
            "name": "T-Shirt",
            "id": 1,
            "checkins": 1,
            "admission": False,
            "total": 1,
            "variations": [
              {
                "name": "Red",
                "id": 1,
                "checkins": 1,
                "total": 12
              },
              {
               "name": "Blue",
                "id": 2,
                "checkins": 4,
                "total": 8
              }
            ]
          },
          {
            "name": "Ticket",
            "id": 2,
            "checkins": 15,
            "admission": True,
            "total": 22,
            "variations": []
          }
        ]
      }

   :query key: Secret API key
   :statuscode 200: Valid request
   :statuscode 404: Unknown organizer or event
   :statuscode 403: Invalid authorization key

.. _pretixdroid Android app: https://github.com/pretix/pretixdroid
