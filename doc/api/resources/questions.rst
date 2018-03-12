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
                                                                 available objects.
├ id                                  integer                    Internal ID of the option
├ identifier                          string                     An arbitrary string that can be used for matching with
                                                                 other sources.
└ answer                              multi-lingual string       The displayed value of this option
===================================== ========================== =======================================================

.. versionchanged:: 1.12

  The values ``D``, ``H``, and ``W`` for the field ``type`` are now allowed and the ``ask_during_checkin`` field has
  been added.

.. versionchanged:: 1.14

  The attribute ``identifier`` has been added to both the resource itself and the ``options`` subresource.

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
                "answer": {"en": "S"}
              },
              {
                "id": 2,
                "identifier": "DFEMJWMJ",
                "answer": {"en": "M"}
              },
              {
                "id": 3,
                "identifier": "W9AH7RDE",
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
            "answer": {"en": "S"}
          },
          {
            "id": 2,
            "identifier": "DFEMJWMJ",
            "answer": {"en": "M"}
          },
          {
            "id": 3,
            "identifier": "W9AH7RDE",
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
