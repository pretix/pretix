.. spelling:: checkin

Questions
=========

Resource description
--------------------

Questions define additional fields that need to be filled out by customers during checkout.
The question resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the question
question                              multi-lingual string       The field label shown to the customer
type                                  string                     The expected type of answer. Valid options:

                                                                 * ``N`` – number
                                                                 * ``S`` – one-line string
                                                                 * ``T`` – multi-line string
                                                                 * ``B`` – boolean
                                                                 * ``C`` – choice from a list
                                                                 * ``M`` – multiple choice from a list
                                                                 * ``F`` – file upload
                                                                 * ``D`` – date
                                                                 * ``H`` – time
                                                                 * ``W`` – date and time
required                              boolean                    If ``True``, the question needs to be filled out.
position                              integer                    An integer, used for sorting
items                                 list of integers           List of item IDs this question is assigned to.
identifier                            string                     An arbitrary string that can be used for matching with
                                                                 other sources.
ask_during_checkin                    boolean                    If ``True``, this question will not be asked while
                                                                 buying the ticket, but will show up when redeeming
                                                                 the ticket instead.
options                               list of objects            In case of question type ``C`` or ``M``, this lists the
                                                                 available objects. Only writable during creation,
                                                                 use separate endpoint to modify this later.
├ id                                  integer                    Internal ID of the option
├ position                            integer                    An integer, used for sorting
├ identifier                          string                     An arbitrary string that can be used for matching with
                                                                 other sources.
└ answer                              multi-lingual string       The displayed value of this option
===================================== ========================== =======================================================

.. versionchanged:: 1.12

  The values ``D``, ``H``, and ``W`` for the field ``type`` are now allowed and the ``ask_during_checkin`` field has
  been added.

.. versionchanged:: 1.14

  Write methods have been added. The attribute ``identifier`` has been added to both the resource itself and the
  options resource. The ``position`` attribute has been added to the options resource.

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/questions/

   Returns a list of all questions within a given event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/questions/ HTTP/1.1
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
            "question": {"en": "T-Shirt size"},
            "type": "C",
            "required": false,
            "items": [1, 2],
            "position": 1,
            "identifier": "WY3TP9SL",
            "ask_during_checkin": false,
            "options": [
              {
                "id": 1,
                "identifier": "LVETRWVU",
                "position": 0,
                "answer": {"en": "S"}
              },
              {
                "id": 2,
                "identifier": "DFEMJWMJ",
                "position": 1,
                "answer": {"en": "M"}
              },
              {
                "id": 3,
                "identifier": "W9AH7RDE",
                "position": 2,
                "answer": {"en": "L"}
              }
            ]
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query string ordering: Manually set the ordering of results. Valid fields to be used are ``id`` and ``position``.
                           Default: ``position``
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/questions/(id)/

   Returns information on one question, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/questions/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "question": {"en": "T-Shirt size"},
        "type": "C",
        "required": false,
        "items": [1, 2],
        "position": 1,
        "identifier": "WY3TP9SL",
        "ask_during_checkin": false,
        "options": [
          {
            "id": 1,
            "identifier": "LVETRWVU",
            "position": 1,
            "answer": {"en": "S"}
          },
          {
            "id": 2,
            "identifier": "DFEMJWMJ",
            "position": 2,
            "answer": {"en": "M"}
          },
          {
            "id": 3,
            "identifier": "W9AH7RDE",
            "position": 3,
            "answer": {"en": "L"}
          }
        ]
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the question to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/questions/

   Creates a new question

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/questions/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content: application/json

      {
        "question": {"en": "T-Shirt size"},
        "type": "C",
        "required": false,
        "items": [1, 2],
        "position": 1,
        "ask_during_checkin": false,
        "options": [
          {
            "answer": {"en": "S"}
          },
          {
            "answer": {"en": "M"}
          },
          {
            "answer": {"en": "L"}
          }
        ]
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json


      {
        "id": 1,
        "question": {"en": "T-Shirt size"},
        "type": "C",
        "required": false,
        "items": [1, 2],
        "position": 1,
        "identifier": "WY3TP9SL",
        "ask_during_checkin": false,
        "options": [
          {
            "id": 1,
            "identifier": "LVETRWVU",
            "position": 1,
            "answer": {"en": "S"}
          },
          {
            "id": 2,
            "identifier": "DFEMJWMJ",
            "position": 2,
            "answer": {"en": "M"}
          },
          {
            "id": 3,
            "identifier": "W9AH7RDE",
            "position": 3,
            "answer": {"en": "L"}
          }
        ]
      }

   :param organizer: The ``slug`` field of the organizer of the event to create an item for
   :param event: The ``slug`` field of the event to create an item for
   :statuscode 201: no error
   :statuscode 400: The item could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/questions/(id)/

   Update a question. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   You can change all fields of the resource except the ``options`` field. If
   you need to update/delete options please use the nested dedicated endpoints.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/items/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "position": 2
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "question": {"en": "T-Shirt size"},
        "type": "C",
        "required": false,
        "items": [1, 2],
        "position": 2,
        "identifier": "WY3TP9SL",
        "ask_during_checkin": false,
        "options": [
          {
            "id": 1,
            "identifier": "LVETRWVU",
            "position": 1,
            "answer": {"en": "S"}
          },
          {
            "id": 2,
            "identifier": "DFEMJWMJ",
            "position": 2,
            "answer": {"en": "M"}
          },
          {
            "id": 3,
            "identifier": "W9AH7RDE",
            "position": 3,
            "answer": {"en": "L"}
          }
        ]
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the question to modify
   :statuscode 200: no error
   :statuscode 400: The item could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to change this resource.

.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/questions/(id)/

   Delete a question.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/items/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the item to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to delete this resource.
