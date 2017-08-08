Tax rules
=========

Resource description
--------------------

Tax rules specify how tax should be calculated for specific products.

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

.. versionchanged:: 1.7

   This resource has been added.


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
      Content-Type: text/javascript

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
      Content-Type: text/javascript

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
   :param id: The ``slug`` field of the sub-event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view it.
