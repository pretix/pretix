.. _rest-taxrules:

Tax rules
=========

Resource description
--------------------

Tax rules specify how tax should be calculated for specific products. Custom taxation rule sets are currently to
available via the API.

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the tax rule
name                                  multi-lingual string       The tax rules' name
rate                                  decimal (string)           Tax rate in percent
price_includes_tax                    boolean                    If ``true`` (default), tax is assumed to be included in
                                                                 the specified product price
eu_reverse_charge                     boolean                    If ``true``, EU reverse charge rules are applied
home_country                          string                     Merchant country (required for reverse charge), can be
                                                                 ``null`` or empty string
===================================== ========================== =======================================================


Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/taxrules/

   Returns a list of all tax rules configured for an event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/taxrules/ HTTP/1.1
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
            "name": {"en": "VAT"},
            "rate": "19.00",
            "price_includes_tax": true,
            "eu_reverse_charge": false,
            "home_country": "DE"
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/taxrules/(id)/

   Returns information on one tax rule, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/taxrules/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "name": {"en": "VAT"},
        "rate": "19.00",
        "price_includes_tax": true,
        "eu_reverse_charge": false,
        "home_country": "DE"
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the tax rule to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event/rule does not exist **or** you have no permission to view it.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/taxrules/

   Create a new tax rule.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/taxrules/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 166

      {
        "name": {"en": "VAT"},
        "rate": "19.00",
        "price_includes_tax": true,
        "eu_reverse_charge": false,
        "home_country": "DE"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "name": {"en": "VAT"},
        "rate": "19.00",
        "price_includes_tax": true,
        "eu_reverse_charge": false,
        "home_country": "DE"
      }

   :param organizer: The ``slug`` field of the organizer to create a tax rule for
   :param event: The ``slug`` field of the event to create a tax rule for
   :statuscode 201: no error
   :statuscode 400: The tax rule could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create tax rules.


.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/taxrules/(id)/

   Update a tax rule. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/taxrules/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 34

      {
        "rate": "20.00",
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: text/javascript

      {
        "id": 1,
        "name": {"en": "VAT"},
        "rate": "20.00",
        "price_includes_tax": true,
        "eu_reverse_charge": false,
        "home_country": "DE"
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the tax rule to modify
   :statuscode 200: no error
   :statuscode 400: The tax rule could not be modified due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event/rule does not exist **or** you have no permission to change it.


.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/taxrules/(id)/

   Delete a tax rule. Note that tax rules can only be deleted if they are not in use for any products, settings
   or orders. If you cannot delete a tax rule, this method will return a ``403`` status code and you can only
   discontinue using it everywhere else.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/taxrules/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the tax rule to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event/rule does not exist **or** you have no permission to change it **or** this tax rule cannot be deleted since it is currently in use.
