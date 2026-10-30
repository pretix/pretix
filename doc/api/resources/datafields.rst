
.. _rest-datafields:

Data fields
=========

Resource description
--------------------

Data fields define additional fields related to an order or an order position.
By referencing data fields in a questionnaire, you can have customers or staff fill them out -- during or
after checkout (web or POS), during check-in in the ticket scanner app, or in the backend.

There are two different resource paths for data fields, depending on whether the data field is attached
to orders or order positions. Therefore, each endpoint below has two different URLs.

The data field resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the data field
internal_name                         string                     An internal field label
identifier                            string                     An arbitrary string that can be used for matching with
                                                                 other sources.
                                                                 Must be unique per event, across all types of data fields.
type                                  string                     The expected type of data. Valid options:

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
                                                                 * ``TEL`` – telephone number
show_during_checkin                   boolean                    If ``true``, the value of the data field will be shown
                                                                 during check-in (if the check-in client supports it).
print_on_invoice                      boolean                    If ``true``, the data field will be shown on
                                                                 invoices.
options                               list of objects            In case of data field type ``C`` or ``M``, this lists the
                                                                 available objects. Only writable during creation,
                                                                 use :ref:`separate endpoint <rest-datafieldoptions>` to modify this later.
├ id                                  integer                    Internal ID of the option
├ position                            integer                    An integer, used for sorting
├ identifier                          string                     An arbitrary string that can be used for matching with
                                                                 other sources.
└ answer                              multi-lingual string       The displayed value of this option
valid_number_min                      string                     Minimum value for number fields (optional)
valid_number_max                      string                     Maximum value for number fields (optional)
valid_date_min                        date                       Minimum value for date fields (optional)
valid_date_max                        date                       Maximum value for date fields (optional)
valid_datetime_min                    datetime                   Minimum value for date and time fields (optional)
valid_datetime_max                    datetime                   Maximum value for date and time fields (optional)
valid_file_portrait                   boolean                    Turn on file validation for portrait photos
valid_string_length_min               integer                    Minimum length for string fields (optional)
valid_string_length_max               integer                    Maximum length for string fields (optional)
referenced_by_questionnaires          list of integers           **Read-only.** List of questionnaire IDs that reference
                                                                 this data field
===================================== ========================== =======================================================

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/datafields/position/
              /api/v1/organizers/(organizer)/events/(event)/datafields/order/

   Returns a list of all data fields within a given event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/datafields/position/ HTTP/1.1
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
            "internal_name": "T-Shirt size",
            "type": "C",
            "identifier": "WY3TP9SL",
            "show_during_checkin": false,
            "print_on_invoice": false,
            "valid_number_min": null,
            "valid_number_max": null,
            "valid_date_min": null,
            "valid_date_max": null,
            "valid_datetime_min": null,
            "valid_datetime_max": null,
            "valid_string_length_min": null,
            "valid_string_length_max": null,
            "valid_file_portrait": false,
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
            ],
            "referenced_by_questionnaires": [1]
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

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/datafields/position/(id)/
              /api/v1/organizers/(organizer)/events/(event)/datafields/order/(id)/

   Returns information on one data field, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/datafields/position/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "internal_name": "T-Shirt size",
        "type": "C",
        "identifier": "WY3TP9SL",
        "show_during_checkin": false,
        "print_on_invoice": false,
        "valid_number_min": null,
        "valid_number_max": null,
        "valid_date_min": null,
        "valid_date_max": null,
        "valid_datetime_min": null,
        "valid_datetime_max": null,
        "valid_string_length_min": null,
        "valid_string_length_max": null,
        "valid_file_portrait": false,
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
        ],
        "referenced_by_questionnaires": [1]
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the question to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/datafields/position/
               /api/v1/organizers/(organizer)/events/(event)/datafields/order/

   Create a new question

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/datafields/position/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "internal_name": "T-Shirt size",
        "type": "C",
        "show_during_checkin": false,
        "print_on_invoice": false,
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
        "internal_name": "T-Shirt size",
        "type": "C",
        "identifier": "WY3TP9SL",
        "show_during_checkin": false,
        "print_on_invoice": false,
        "valid_number_min": null,
        "valid_number_max": null,
        "valid_date_min": null,
        "valid_date_max": null,
        "valid_datetime_min": null,
        "valid_datetime_max": null,
        "valid_string_length_min": null,
        "valid_string_length_max": null,
        "valid_file_portrait": false,
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
        ],
        "referenced_by_questionnaires": [1]
      }

   :param organizer: The ``slug`` field of the organizer of the event to create an item for
   :param event: The ``slug`` field of the event to create an item for
   :statuscode 201: no error
   :statuscode 400: The item could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/datafields/position/(id)/
                /api/v1/organizers/(organizer)/events/(event)/datafields/order/(id)/

   Update a data field. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   You can change all fields of the resource except the ``options`` field. If
   you need to update/delete options please use the nested dedicated endpoints.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/datafields/position/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "internal_name": "Clothing size"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "internal_name": "Clothing size",
        "type": "C",
        "identifier": "WY3TP9SL",
        "show_during_checkin": false,
        "print_on_invoice": false,
        "valid_number_min": null,
        "valid_number_max": null,
        "valid_date_min": null,
        "valid_date_max": null,
        "valid_datetime_min": null,
        "valid_datetime_max": null,
        "valid_string_length_min": null,
        "valid_string_length_max": null,
        "valid_file_portrait": false,
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
        ],
        "referenced_by_questionnaires": [1]
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the question to modify
   :statuscode 200: no error
   :statuscode 400: The question could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to change this resource.

.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/datafields/position/(id)/
                 /api/v1/organizers/(organizer)/events/(event)/datafields/order/(id)/

   Delete a data field.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/datafields/position/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the question to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to delete this resource.


