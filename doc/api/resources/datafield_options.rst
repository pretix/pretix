
.. _rest-datafieldoptions:

Data field options
================

As with data fields, data field options exist on two resource paths, depending on whether
the data field is attached to orders or order positions. Therefore, each endpoint below has two
different URLs.

Resource description
--------------------

Data fields of type "choice" or "multiple choice" can have different options attached.
The options resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the option
position                              integer                    An integer, used for sorting
identifier                            string                     An arbitrary string that can be used for matching with
                                                                 other sources.
answer                                multi-lingual string       The displayed value of this option
===================================== ========================== =======================================================

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/datafields/(datafield)/options/
              /api/v1/organizers/(organizer)/events/(event)/orderdatafields/(datafield)/options/

   Returns a list of all options for a given data field.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/datafields/11/options/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "count": 2,
        "next": null,
        "previous": null,
        "results": [
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

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query boolean active: If set to ``true`` or ``false``, only data fields with this value for the field ``active`` will be
                          returned.
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param datafield: The ``id`` field of the data field to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event/data field does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/datafields/(datafield)/options/(id)/
              /api/v1/organizers/(organizer)/events/(event)/orderdatafields/(datafield)/options/(id)/

   Returns information on one option, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/datafields/1/options/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "identifier": "LVETRWVU",
        "position": 1,
        "answer": {"en": "S"}
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param datafield: The ``id`` field of the data field to fetch
   :param id: The ``id`` field of the option to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/datafields/(datafield)/options/
               /api/v1/organizers/(organizer)/events/(event)/orderdatafields/(datafield)/options/

   Creates a new option

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/datafields/1/options/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "identifier": "LVETRWVU",
        "position": 1,
        "answer": {"en": "S"}
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "identifier": "LVETRWVU",
        "position": 1,
        "answer": {"en": "S"}
      }

   :param organizer: The ``slug`` field of the organizer of the event/data field to create a option for
   :param event: The ``slug`` field of the event to create a option for
   :param datafield: The ``id`` field of the data field to create a option for
   :statuscode 201: no error
   :statuscode 400: The option could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/datafields/(datafield)/options/(id)/
                /api/v1/organizers/(organizer)/events/(event)/orderdatafields/(datafield)/options/(id)/

   Update an option. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   You can change all fields of the resource except the ``id`` field.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/datafields/1/options/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "position": 3
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "identifier": "LVETRWVU",
        "position": 1,
        "answer": {"en": "S"}
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the data field to modify
   :param id: The ``id`` field of the option to modify
   :statuscode 200: no error
   :statuscode 400: The option could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to change this resource.

.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/datafields/(datafield)/options/(id)/
                 /api/v1/organizers/(organizer)/events/(event)/orderdatafields/(datafield)/options/(id)/

   Delete an option.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/datafields/1/options/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param datafield: The ``id`` field of the data field to modify
   :param id: The ``id`` field of the option to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to delete this resource.
