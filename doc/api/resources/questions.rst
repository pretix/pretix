.. spelling:: checkin

.. _rest-questions:

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
                                                                 * ``CC`` – country code (ISO 3666-1 alpha-2)
required                              boolean                    If ``true``, the question needs to be filled out.
position                              integer                    An integer, used for sorting
items                                 list of integers           List of item IDs this question is assigned to.
identifier                            string                     An arbitrary string that can be used for matching with
                                                                 other sources.
ask_during_checkin                    boolean                    If ``true``, this question will not be asked while
                                                                 buying the ticket, but will show up when redeeming
                                                                 the ticket instead.
hidden                                boolean                    If ``true``, the question will only be shown in the
                                                                 backend.
options                               list of objects            In case of question type ``C`` or ``M``, this lists the
                                                                 available objects. Only writable during creation,
                                                                 use separate endpoint to modify this later.
├ id                                  integer                    Internal ID of the option
├ position                            integer                    An integer, used for sorting
├ identifier                          string                     An arbitrary string that can be used for matching with
                                                                 other sources.
└ answer                              multi-lingual string       The displayed value of this option
dependency_question                   integer                    Internal ID of a different question. The current
                                                                 question will only be shown if the question given in
                                                                 this attribute is set to the value given in
                                                                 ``dependency_value``. This cannot be combined with
                                                                 ``ask_during_checkin``.
dependency_value                      string                     The value ``dependency_question`` needs to be set to.
                                                                 If ``dependency_question`` is set to a boolean
                                                                 question, this should be ``"true"`` or ``"false"``.
                                                                 Otherwise, it should be the ``identifier`` of a
                                                                 question option.
===================================== ========================== =======================================================

.. versionchanged:: 1.12

  The values ``D``, ``H``, and ``W`` for the field ``type`` are now allowed and the ``ask_during_checkin`` field has
  been added.

.. versionchanged:: 1.14

  Write methods have been added. The attribute ``identifier`` has been added to both the resource itself and the
  options resource. The ``position`` attribute has been added to the options resource.

.. versionchanged:: 2.7

  The attribute ``hidden`` and the question type ``CC`` have been added.

Endpoints
---------

.. versionchanged:: 1.15

   The questions endpoint has been extended by the filter queries ``ask_during_checkin``, ``requred``, and
   ``identifier``.

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
            "hidden": false,
            "dependency_question": null,
            "dependency_value": null,
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
   :query string identifier: Only return questions with the given identifier string
   :query boolean ask_during_checkin: Only return questions that are or are not to be asked during check-in
   :query boolean required: Only return questions that are or are not required to fill in
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
        "hidden": false,
        "dependency_question": null,
        "dependency_value": null,
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
      Content-Type: application/json

      {
        "question": {"en": "T-Shirt size"},
        "type": "C",
        "required": false,
        "items": [1, 2],
        "position": 1,
        "ask_during_checkin": false,
        "hidden": false,
        "dependency_question": null,
        "dependency_value": null,
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
        "hidden": false,
        "dependency_question": null,
        "dependency_value": null,
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
        "hidden": false,
        "dependency_question": null,
        "dependency_value": null,
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
