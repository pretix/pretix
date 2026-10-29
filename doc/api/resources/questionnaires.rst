
.. _rest-questionnaires:

Questionnaires
=========

Questionnaires are attached to one or more products, and a product can have multiple questionnaires.
They consist of questionnaire children, each of which can be one of the following:

Reference to system field
    To reference a system field, use one of the identifier strings from the table below in the child's `datafield` attribute.
    Currently, system fields are only defined on order positions, not on orders.

    =============== =========================== ============================
    Container       Identifier                  Label
    =============== =========================== ============================
    Order position  `"@attendee_name_parts"`     Attendee name
    Order position  `"@attendee_email"`          Attendee email
    Order position  `"@company"`                 Company
    Order position  `"@street"`                  Street
    Order position  `"@zipcode"`                 ZIP code
    Order position  `"@city"`                    City
    Order position  `"@state"`                   State
    Order position  `"@country"`                 Country
    =============== =========================== ============================


Reference to user-defined data field
    To reference a :ref:`user-defined data field <rest-datafields>`, use its internal reference (`identifier`) in the child's `datafield` attribute.


Static explanation text / subheading
    To add a static text block, set the child's `datafield` attribute to `null`.


Resource description
--------------------


.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the questionnaire
type                                  string                     The type of questionnaire. Valid options:

                                                                 * ``order_presale`` — Order-wide, before purchase
                                                                 * ``position_presale`` — Per product, before purchase
                                                                 * ``position_attendee`` — Per product, via attendee link
                                                                 * ``position_checkin`` — Per product, at check-in
                                                                 * ``position_hidden`` — Per product, hidden
internal_name                         string                     Internal label for the questionnaire
items                                 list of integers           List of item IDs this questionnaire is assigned to.
position                              integer                    An integer, used for sorting
all_sales_channels                    boolean                    If ``true`` (default), the questions from this questionnaire
                                                                 are asked on all sales channels.
limit_sales_channels                  list of strings            List of sales channel identifiers the questions are asked on
                                                                 if ``all_sales_channels`` is ``false``.
children                              list of objects            List of all questionnaire children.
├ datafield                           string                     Reference to a data field (see above)
├ required                            boolean                    If ``true``, the question needs to be filled out.
├ label                               multi-lingual string       The field label shown to the customer
├ help_text                           multi-lingual string       The help text shown to the customer
├ dependency_question                 string                     ``datafield`` reference of a different child of the same
                                                                 questionnaire.
                                                                 The current question will only be shown if the question
                                                                 given in this attribute is set to one of the values given
                                                                 in ``dependency_values``.
├ dependency_values                   list of strings            If ``dependency_question`` is set to a boolean
                                                                 question, this should be ``["True"]`` or ``["False"]``.
                                                                 Otherwise, it should be a list of ``identifier`` values
                                                                 of question options.
├ rendered_help_text                  multi-lingual string       **Read-only.** Markdown contents from help_text rendered
                                                                 to HTML
===================================== ========================== =======================================================


Endpoints
---------


.. http:get:: /api/v1/organizers/(organizer)/events/(event)/questionnaires/

   Returns a list of all questionnaires within a given event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/questionnaires/ HTTP/1.1
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
            "type": "position_presale",
            "internal_name": "Attendee data",
            "items": [1, 2],
            "position": 0,
            "all_sales_channels": true,
            "limit_sales_channels": [],
            "children": [
              {
                "datafield": "@attendee_name_parts",
                "required": false,
                "label": {"en": "Attendee name"},
                "help_text": {},
                "dependency_question": null,
                "dependency_values": [],
                "rendered_help_text": ""
              },
              {
                "datafield": "@attendee_email",
                "required": false,
                "label": {"en": "Attendee email"},
                "help_text": {},
                "dependency_question": null,
                "dependency_values": [],
                "rendered_help_text": ""
              }
            ]
          },
          {
            "id": 2,
            "type": "order_presale",
            "internal_name": "Per-order questions",
            "items": [],
            "position": 0,
            "all_sales_channels": true,
            "limit_sales_channels": [],
            "children": [
              {
                "datafield": "87Y8DCS9",
                "required": false,
                "label": {"en": "How did you find us?"},
                "help_text": {},
                "dependency_question": null,
                "dependency_values": [],
                "rendered_help_text": ""
              }
            ]
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query string ordering: Manually set the ordering of results. Valid fields to be used are ``id`` and ``position``.
                           Default: ``position``
   :query string type: Only return questionnaires with the given type
   :query string items: Only return questionnaires associated with the given item (internal item ID)
   :query boolean sales_channel: Only return questionnaires visible on the given sales channel (sales channel identifier string)
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/questionnaires/(id)/

   Returns information on one questionnaire, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/questionnaires/2/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 2,
        "type": "order_presale",
        "internal_name": "Per-order questions",
        "items": [],
        "position": 0,
        "all_sales_channels": true,
        "limit_sales_channels": [],
        "children": [
          {
            "datafield": "87Y8DCS9",
            "required": false,
            "label": {"en": "How did you find us?"},
            "help_text": {},
            "dependency_question": null,
            "dependency_values": [],
            "rendered_help_text": ""
          }
        ]
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the questionnaire to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/questionnaires/

   Create a new questionnaire

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/questionnaires/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "type": "order_presale",
        "internal_name": "Per-order questions",
        "position": 0,
        "all_sales_channels": true,
        "children": [
          {
            "datafield": "87Y8DCS9",
            "required": false,
            "label": {"en": "How did you find us?"}
          }
        ]
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 2,
        "type": "order_presale",
        "internal_name": "Per-order questions",
        "items": [],
        "position": 0,
        "all_sales_channels": true,
        "limit_sales_channels": [],
        "children": [
          {
            "datafield": "87Y8DCS9",
            "required": false,
            "label": {"en": "How did you find us?"},
            "help_text": {},
            "dependency_question": null,
            "dependency_values": [],
            "rendered_help_text": ""
          }
        ]
      }


   :param organizer: The ``slug`` field of the organizer of the event to create a questionnaire for
   :param event: The ``slug`` field of the event to create a questionnaire for
   :statuscode 201: no error
   :statuscode 400: The questionnaire could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/questionnaires/(id)/

   Update a questionnaire. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   You can only change all ``children`` en bloc, or keep all of them unchanged in case of a ``PATCH``. If you
   change ``children``, you need to specify all fields of the resource.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/questionnaires/2/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "internal_name": "Questions asked per order"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 2,
        "type": "order_presale",
        "internal_name": "Questions asked per order",
        "items": [],
        "position": 0,
        "all_sales_channels": true,
        "limit_sales_channels": [],
        "children": [
          {
            "datafield": "87Y8DCS9",
            "required": false,
            "label": {"en": "How did you find us?"},
            "help_text": {},
            "dependency_question": null,
            "dependency_values": [],
            "rendered_help_text": ""
          }
        ]
      }

   :param organizer: The ``slug`` field of the organizer of the questionnaire to modify
   :param event: The ``slug`` field of the event of the questionnaire to modify
   :param id: The ``id`` field of the questionnaire to modify
   :statuscode 200: no error
   :statuscode 400: The questionnaire could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to change this resource.

.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/questionnaires/(id)/

   Delete a questionnaire.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/questionnaires/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer of the questionnaire to modify
   :param event: The ``slug`` field of the event of the questionnaire to modify
   :param id: The ``id`` field of the questionnaire to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to delete this resource.
