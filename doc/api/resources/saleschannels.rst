Sales channels
==============

Resource description
--------------------

The sales channel resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
identifier                            string                     Internal ID of the sales channel. For sales channel types
                                                                 that allow only one instance, this is the same as ``type``.
                                                                 For sales channel types that allow multiple instances, this
                                                                 is always prefixed with ``type.``.
label                                 multi-lingual string       Human-readable name of the sales channel
type                                  string                     Type of the sales channel. Only channels with type ``api``
                                                                 can currently be created through the API.
position                              integer                    Position for sorting lists of sales channels
===================================== ========================== =======================================================

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/saleschannels/

   Returns a list of all sales channels within a given organizer.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/saleschannels/ HTTP/1.1
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
            "identifier": "web",
            "label": {
              "en": "Online shop"
            },
            "type": "web",
            "position": 0
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of the organizer to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/saleschannels/(identifier)/

   Returns information on one sales channel, identified by its identifier.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/saleschannels/web/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "identifier": "web",
        "label": {
          "en": "Online shop"
        },
        "type": "web",
        "position": 0
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param identifier: The ``identifier`` field of the sales channel to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/saleschannels/

   Creates a sales channel

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/saleschannels/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "identifier": "api.custom",
        "label": {
          "en": "Custom integration"
        },
        "type": "api",
        "position": 2
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "identifier": "api.custom",
        "label": {
          "en": "Custom integration"
        },
        "type": "api",
        "position": 2
      }

   :param organizer: The ``slug`` field of the organizer to create a sales channel for
   :statuscode 201: no error
   :statuscode 400: The sales channel could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/saleschannels/(identifier)/

   Update a sales channel. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   You can change all fields of the resource except the ``identifier`` and ``type`` fields.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/saleschannels/web/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "position": 5
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "identifier": "web",
        "label": {
          "en": "Online shop"
        },
        "type": "web",
        "position": 5
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param identifier: The ``identifier`` field of the sales channel to modify
   :statuscode 200: no error
   :statuscode 400: The sales channel could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to change this resource.

.. http:delete:: /api/v1/organizers/(organizer)/saleschannels/(identifier)/

   Delete a sales channel. You can not delete sales channels which have already been used or which are integral parts
   of the system.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/saleschannels/api.custom/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param identifier: The ``identifier`` field of the sales channel to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to delete this resource **or** the sales channel is currently in use.
