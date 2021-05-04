Membership types
================

Resource description
--------------------

The membership type resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the membership type
name                                  multi-lingual string       Human-readable name of the type
transferable                          boolean                    Whether a membership of this type can be used by
                                                                 multiple persons
allow_parallel_usage                  boolean                    Whether a membership of this type can be used for
                                                                 multiple parallel tickets
max_usages                            integer                    Maximum number of times a membership of this type can be
                                                                 used.
===================================== ========================== =======================================================

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/membershiptypes/

   Returns a list of all membership types within a given organizer.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/membershiptypes/ HTTP/1.1
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
            "name": {
              "de": "Wochenkarte",
              "en": "Week pass"
            },
            "transferable": false,
            "allow_parallel_usage": false,
            "max_usages": 7
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of the organizer to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/membershiptypes/(id)/

   Returns information on one membership type, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/membershiptypes/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "name": {
          "de": "Wochenkarte",
          "en": "Week pass"
        },
        "transferable": false,
        "allow_parallel_usage": false,
        "max_usages": 7
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param id: The ``id`` field of the membership type to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/membershiptypes/

   Creates a new membership type

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/membershiptypes/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "name": {
          "de": "Wochenkarte",
          "en": "Week pass"
        },
        "transferable": false,
        "allow_parallel_usage": false,
        "max_usages": 7
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 3,
        "name": {
          "de": "Wochenkarte",
          "en": "Week pass"
        },
        "transferable": false,
        "allow_parallel_usage": false,
        "max_usages": 7
      }

   :param organizer: The ``slug`` field of the organizer to create a membership type for
   :statuscode 201: no error
   :statuscode 400: The membership type could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/membershiptypes/(id)/

   Update a membership type. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   You can change all fields of the resource except the ``id`` field.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/membershiptypes/2/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "max_usages": 3
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 2,
        "name": {
          "de": "Wochenkarte",
          "en": "Week pass"
        },
        "transferable": false,
        "allow_parallel_usage": false,
        "max_usages": 3
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param id: The ``id`` field of the membership type to modify
   :statuscode 200: no error
   :statuscode 400: The membership could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to change this resource.

.. http:delete:: /api/v1/organizers/(organizer)/membershiptypes/(id)/

   Delete a membership type. You can not delete types which have already been used.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/membershiptype/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param id: The ``id`` field of the type to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to delete this resource **or** the membership type is currently in use.
