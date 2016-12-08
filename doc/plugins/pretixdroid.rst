pretixdroid HTTP API
====================

The pretixdroid plugin provides a HTTP API that the `pretixdroid Android app`_
uses to communicate with the pretix server.

.. http:post:: /pretixdroid/api/(organizer)/(event)/redeem/

   Redeems a ticket, i.e. checks the user in.

   **Example request**:

   .. sourcecode:: http

      POST /pretixdroid/api/demoorga/democon/redeem/?key=ABCDEF HTTP/1.1
      Host: demo.pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/x-www-form-urlencoded

      secret=az9u4mymhqktrbupmwkvv6xmgds5dk3

   **Example successful response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: text/json

      {
        'status': 'ok'
        'version': 2
      }

   **Example error response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: text/json

      {
        'status': 'error',
        'reason': 'already_redeemed',
        'version': 2
      }

   Possible error reasons:

   * ``unpaid`` - Ticket is not paid for or has been refunded
   * ``already_redeemed`` - Ticket already has been redeemed
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
        'results': [
          {
            'secret': 'az9u4mymhqktrbupmwkvv6xmgds5dk3',
            'order': 'ABCE6',
            'item': 'Standard ticket',
            'variation': null,
            'attendee_name': 'Peter Higgs',
            'redeemed': false,
            'paid': true
          },
          ...
        ],
        'version': 2
      }

   :query query: Search query
         :query key: Secret API key
         :statuscode 200: Valid request
         :statuscode 404: Unknown organizer or event
         :statuscode 403: Invalid authorization key

.. http:get:: /pretixdroid/api/(organizer)/(event)/status/

   Returns status information, such as the total number of tickets and the
   number of performed checkins.

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
        'checkins': 17,
        'total': 42,
        'version': 2,
        'items': [
          {
            'name': 'T-Shirt',
            'id': 1,
            'checkins': 1,
            'admission': False,
            'total': 1,
            'variations': [
              {
                'name': 'Red',
                'id': 1,
                'checkins': 1,
                'total': 12
              },
              {
               'name': 'Blue',
                'id': 2,
                'checkins': 4,
                'total': 8
              }
            ]
          },
          {
            'name': 'Ticket',
            'id': 2,
            'checkins': 15,
            'admission': True,
            'total': 22,
            'variations': []
          }
        ]
      }

   :query key: Secret API key
   :statuscode 200: Valid request
   :statuscode 404: Unknown organizer or event
   :statuscode 403: Invalid authorization key

.. _pretixdroid Android app: https://github.com/pretix/pretixdroid
