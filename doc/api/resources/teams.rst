.. _`rest-teams`:

Teams
=====

.. warning:: Unlike our user interface, the team API **does** allow you to lock yourself out by deleting or modifying
             the team your user or API key belongs to. Be careful around here!

Team resource
-------------

The team resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the team
name                                  string                     Team name
all_events                            boolean                    Whether this team has access to all events
limit_events                          list                       List of event slugs this team has access to
can_create_events                     boolean
can_change_teams                      boolean
can_change_organizer_settings         boolean
can_manage_gift_cards                 boolean
can_change_event_settings             boolean
can_change_items                      boolean
can_view_orders                       boolean
can_change_orders                     boolean
can_view_vouchers                     boolean
can_change_vouchers                   boolean
===================================== ========================== =======================================================

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/teams/

   Returns a list of all teams within a given organizer.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/teams/ HTTP/1.1
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
            "name": "Admin team",
            "all_events": true,
            "limit_events": [],
            "can_create_events": true,
            ...
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of the organizer to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/teams/(id)/

   Returns information on one team, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/teams/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "name": "Admin team",
        "all_events": true,
        "limit_events": [],
        "can_create_events": true,
        ...
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param id: The ``id`` field of the team to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/teams/

   Creates a new team

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/teams/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "name": "Admin team",
        "all_events": true,
        "limit_events": [],
        "can_create_events": true,
        ...
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 2,
        "name": "Admin team",
        "all_events": true,
        "limit_events": [],
        "can_create_events": true,
        ...
      }

   :param organizer: The ``slug`` field of the organizer to create a team for
   :statuscode 201: no error
   :statuscode 400: The team could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/teams/(id)/

   Update a team. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/teams/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "can_create_events": true
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "name": "Admin team",
        "all_events": true,
        "limit_events": [],
        "can_create_events": true,
        ...
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param id: The ``id`` field of the team to modify
   :statuscode 200: no error
   :statuscode 400: The team could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to change this resource.

.. http:delete:: /api/v1/organizers/(organizer)/teams/(id)/

   Deletes a team.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/teams/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content

   :param organizer: The ``slug`` field of the organizer to modify
   :param id: The ``id`` field of the team to delete
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to change this resource.
