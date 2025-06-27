.. spelling:word-list::

   EN16931
   DSFinV-K

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
internal_name                         string                     An optional name that is only used in the backend
rate                                  decimal (string)           Tax rate in percent
code                                  string                     Codified reason for tax rate (or ``null``), see :ref:`rest-taxcodes`.
price_includes_tax                    boolean                    If ``true`` (default), tax is assumed to be included in
                                                                 the specified product price
default                               boolean                    If ``true`` (default), this is the default tax rate for this event
                                                                 (there can only be one per event).
eu_reverse_charge                     boolean                    **DEPRECATED**. If ``true``, EU reverse charge rules
                                                                 are applied. Will be ignored if custom rules are set.
                                                                 Use custom rules instead.
home_country                          string                     Merchant country (required for reverse charge), can be
                                                                 ``null`` or empty string
keep_gross_if_rate_changes            boolean                    If ``true``, changes of the tax rate based on custom
                                                                 rules keep the gross price constant (default is ``false``)
custom_rules                          object                     Dynamic rules specification. Each list element
                                                                 corresponds to one rule that will be processed in order.
                                                                 The current version of the schema in use can be found
                                                                 `here`_.
===================================== ========================== =======================================================


.. versionchanged:: 2023.6

    The ``custom_rules`` attribute has been added.

.. versionchanged:: 2023.8

    The ``code`` attribute has been added.

.. versionchanged:: 2025.4

    The ``default`` attribute has been added.

.. _rest-taxcodes:

Tax codes
---------

For integration with external systems, such as electronic invoicing or bookkeeping systems, the tax rate itself is often
not sufficient information. For example, there could be many different reasons why a sale has a tax rate of 0 %, but the
external handling of the transaction depends on which reason applies. Therefore, pretix allows to supply a codified
reason that allows us to understand what the specific legal situation is. These tax codes are modeled after a combination
of the code lists from the European standard EN16931 and the German standard DSFinV-K.

The following codes are supported:

- ``S/standard`` -- Standard VAT rate in the merchant country
- ``S/reduced`` -- Reduced VAT rate in the merchant country
- ``S/averaged`` -- Averaged VAT rate in the merchant country (known use case: agricultural businesses in Germany)
- ``AE`` -- Reverse charge
- ``O`` -- Services outside of scope of tax
- ``E`` -- Exempt from tax (no reason given)
- ``E/<reason>`` -- Exempt from tax, where ``<reason>`` is one of the codes listed in the `VATEX code list`_ version 5.0.
- ``Z`` -- Zero-rated goods
- ``G`` -- Free export item, VAT not charged
- ``K`` -- VAT exempt for EEA intra-community supply of goods and services
- ``L`` -- Canary Islands general indirect tax
- ``M`` -- Tax for production, services and importation in Ceuta and Melilla
- ``B`` -- Transferred (VAT), only in Italy

The code set in the ``code`` attribute of the tax rule is used by default. When ``eu_reverse_charge`` is active, the
code is replaced by ``AE`` for reverse charge sales and by ``O`` for non-EU sales. When configuring custom rules, you
should actively set a ``"code"`` key on each rule. Only for ``"action": "reverse"`` we automatically apply the code
``AE``, in all other cases the default ``code`` of the tax rule is selected.

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
            "default": true,
            "internal_name": "VAT",
            "code": "S/standard",
            "rate": "19.00",
            "price_includes_tax": true,
            "eu_reverse_charge": false,
            "keep_gross_if_rate_changes": false,
            "custom_rules": null,
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
            "default": true,
        "internal_name": "VAT",
        "code": "S/standard",
        "rate": "19.00",
        "price_includes_tax": true,
        "eu_reverse_charge": false,
        "keep_gross_if_rate_changes": false,
        "custom_rules": null,
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
        "default": false,
        "internal_name": "VAT",
        "code": "S/standard",
        "rate": "19.00",
        "price_includes_tax": true,
        "eu_reverse_charge": false,
        "keep_gross_if_rate_changes": false,
        "custom_rules": null,
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
        "internal_name": "VAT",
        "code": "S/standard",
        "rate": "20.00",
        "price_includes_tax": true,
        "eu_reverse_charge": false,
        "keep_gross_if_rate_changes": false,
        "custom_rules": null,
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

.. _here: https://github.com/pretix/pretix/blob/master/src/pretix/static/schema/tax-rules-custom.schema.json
.. _VATEX code list: https://ec.europa.eu/digital-building-blocks/sites/display/DIGITAL/Registry+of+supporting+artefacts+to+implement+EN16931#RegistryofsupportingartefactstoimplementEN16931-Codelists