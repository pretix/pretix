Memberships
===========

Resource description
--------------------

The membership resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the membership
customer                              string                     Identifier of the customer associated with this membership (can't be changed)
testmode                              boolean                    Whether this is a test membership
membership_type                       integer                    Internal ID of the membership type
date_start                            datetime                   Start of validity
date_end                              datetime                   End of validity
attendee_name_parts                   object                     JSON representation of components of an attendee name (configuration dependent)
===================================== ========================== =======================================================

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/memberships/

   Returns a list of all memberships within a given organizer.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/memberships/ HTTP/1.1
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
            "id": 2,
            "customer": "EGR9SYT",
            "membership_type": 1,
            "testmode": false,
            "date_start": "2021-04-19T00:00:00+02:00",
            "date_end": "2021-04-20T00:00:00+02:00",
            "attendee_name_parts": {
                "_scheme": "title_given_family",
                "family_name": "Doe",
                "given_name": "John",
                "title": ""
            }
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query string customer: A customer identifier to filter for
   :query integer membership_type: A membership type ID to filter for
   :query boolean testmode: Filter for memberships that are (not) in test mode.
   :param organizer: The ``slug`` field of the organizer to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/memberships/(id)/

   Returns information on one membership, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/memberships/2/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 2,
        "customer": "EGR9SYT",
        "membership_type": 1,
        "testmode": false,
        "date_start": "2021-04-19T00:00:00+02:00",
        "date_end": "2021-04-20T00:00:00+02:00",
        "attendee_name_parts": {
            "_scheme": "title_given_family",
            "family_name": "Doe",
            "given_name": "John",
            "title": ""
        }
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param id: The ``id`` field of the membership to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/memberships/

   Creates a new membership

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/memberships/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "membership_type": 2,
        "customer": "EGR9SYT",
        "testmode": false,
        "date_start": "2021-04-19T00:00:00+02:00",
        "date_end": "2021-04-20T00:00:00+02:00",
        "attendee_name_parts": {
            "_scheme": "title_given_family",
            "family_name": "Doe",
            "given_name": "John",
            "title": ""
        }
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 3,
        "membership_type": 2,
        "customer": "EGR9SYT",
        "testmode": false,
        "date_start": "2021-04-19T00:00:00+02:00",
        "date_end": "2021-04-20T00:00:00+02:00",
        "attendee_name_parts": {
            "_scheme": "title_given_family",
            "family_name": "Doe",
            "given_name": "John",
            "title": ""
        }
      }

   :param organizer: The ``slug`` field of the organizer to create a membership for
   :statuscode 201: no error
   :statuscode 400: The membership could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/memberships/(id)/

   Update a membership. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   You can change all fields of the resource except the ``id``, ``customer``, and ``testmode`` fields.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/memberships/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "membership_type": 3
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "membership_type": 3,
        …
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param id: The ``id`` field of the membership to modify
   :statuscode 200: no error
   :statuscode 400: The membership could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to change this resource.

