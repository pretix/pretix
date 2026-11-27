Gates
=====

Gate resource
-------------

The gate resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the gate within this organizer
name                                  string                     gate name
identifier                            string                     Internal identifier to make it easier to match the data with other sources
===================================== ========================== =======================================================

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/gates/

   Returns a list of all gates within a given organizer.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/gates/ HTTP/1.1
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
                "name": "Main door",
                "identifier": "west_entry"
            }
         ]
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/gates/(id)/

   Returns information on one gate, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/gates/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "name": "Main door",
        "identifier": "west_entry"
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param id: The ``id`` of the gate to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/gates/

   Creates a new gate

   You can supply the following fields of the resource:

   * ``name``
   * ``identifier`` (optional, if you do not supply one, it will be auto-generated)

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/gates/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "name": "South gate",
        "identifier": "south_entry",
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 2,
        "name": "South gate",
        "identifier": "south_entry"
      }

   :param organizer: The ``slug`` field of the organizer to create a gate for
   :statuscode 201: no error
   :statuscode 400: The gate could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/gate does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/gates/(id)/

   Update a gate.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/gates/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "name": "Foo"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 2,
        "name": "Foo",
        "identifier": "south_entry"
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param id: The ``id`` field of the gate to modify
   :statuscode 200: no error
   :statuscode 400: The gate could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/gate does not exist **or** you have no permission to change this resource.

.. http:delete:: /api/v1/organizers/(organizer)/gates/(id)/

   Delete a gate.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/gates/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param id: The ``id`` field of the gate to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/gate does not exist **or** you have no permission to change it **or** this gate cannot be deleted since it is currently in use.

