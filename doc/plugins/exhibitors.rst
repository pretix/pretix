Exhibitors
==========

The exhibitors plugin allows to manage exhibitors at your trade show or conference. After signing up your exhibitors
in the system, you can assign vouchers to exhibitors and give them access to the data of these vouchers. The exhibitors
module is also the basis of the pretixLEAD lead scanning application.

.. note:: On pretix Hosted, using the lead scanning feature of the exhibitors plugin can add additional costs
          depending on your contract.


REST API Resource description
-----------------------------

The exhibitors plugin provides a HTTP API that allows you to create new exhibitors.

The exhibitors resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal exhibitor ID in pretix
name                                  string                     Exhibitor name
internal_id                           string                     Can be used for the ID in your exhibition system, your customer ID, etc. Can be ``null``. Maximum 255 characters.
contact_name                          string                     Contact person (or ``null``)
contact_name_parts                    object of strings          Decomposition of contact name (i.e. given name, family name)
contact_email                         string                     Contact person email address (or ``null``)
booth                                 string                     Booth number (or ``null``). Maximum 100 characters.
locale                                string                     Locale for communication with the exhibitor (or ``null``).
access_code                           string                     Access code for the exhibitor to access their data or use the lead scanning app (read-only).
allow_lead_scanning                   boolean                    Enables lead scanning app
allow_lead_access                     boolean                    Enables access to data gathered by the lead scanning app
allow_voucher_access                  boolean                    Enables access to data gathered by exhibitor vouchers
comment                               string                     Internal comment, not shown to exhibitor
===================================== ========================== =======================================================

You can also access the scanned leads through the API which contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
attendee_order                        string                     Order code of the order the scanned attendee belongs to
attendee_positionid                   integer                    ``positionid`` if the attendee within the order specified by ``attendee_order``
rating                                integer                    A rating of 0 to 5 stars (or ``null``)
notes                                 string                     A note taken by the exhibitor after scanning
tags                                  list of strings            Additional tags selected by the exhibitor
first_upload                          datetime                   Date and time of the first upload of this lead
===================================== ========================== =======================================================

REST API Endpoints
------------------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/exhibitors/

   Returns a list of all exhibitors configured for an event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/exhibitors/ HTTP/1.1
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
            "name": "Aperture Science",
            "internal_id": null,
            "contact_name": "Dr Cave Johnson",
            "contact_name_parts": {
                "_scheme": "salutation_title_given_family",
                "family_name": "Johnson",
                "given_name": "Cave",
                "salutation": "",
                "title": "Dr"
            },
            "contact_email": "johnson@as.example.org",
            "booth": "A2",
            "locale": "de",
            "access_code": "VKHZ2FU8",
            "allow_lead_scanning": true,
            "allow_lead_access": true,
            "allow_voucher_access": true,
            "comment": ""
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or event does not exist **or** you have no permission to view it.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/exhibitors/(id)/

   Returns information on one exhibitor, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/exhibitors/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "name": "Aperture Science",
        "internal_id": null,
        "contact_name": "Dr Cave Johnson",
        "contact_name_parts": {
            "_scheme": "salutation_title_given_family",
            "family_name": "Johnson",
            "given_name": "Cave",
            "salutation": "",
            "title": "Dr"
        },
        "contact_email": "johnson@as.example.org",
        "booth": "A2",
        "locale": "de",
        "access_code": "VKHZ2FU8",
        "allow_lead_scanning": true,
        "allow_lead_access": true,
        "allow_voucher_access": true,
        "comment": ""
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the exhibitor to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event/exhibitor does not exist **or** you have no permission to view it.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/exhibitors/(id)/leads/

   Returns a list of all scanned leads of an exhibitor.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/exhibitors/1/leads/ HTTP/1.1
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
            "attendee_order": "T0E7E",
            "attendee_positionid": 1,
            "rating": 1,
            "notes": "",
            "tags": [],
            "first_upload": "2021-07-06T11:03:31.414491+01:00"
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the exhibitor to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or event or exhibitor does not exist **or** you have no permission to view it.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/exhibitors/

   Create a new exhibitor.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/exhibitors/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 166

      {
        "name": "Aperture Science",
        "internal_id": null,
        "contact_name_parts": {
            "_scheme": "salutation_title_given_family",
            "family_name": "Johnson",
            "given_name": "Cave",
            "salutation": "",
            "title": "Dr"
        },
        "contact_email": "johnson@as.example.org",
        "booth": "A2",
        "locale": "de",
        "access_code": "VKHZ2FU8",
        "allow_lead_scanning": true,
        "allow_lead_access": true,
        "allow_voucher_access": true,
        "comment": ""
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "name": "Aperture Science",
        "internal_id": null,
        "contact_name": "Dr Cave Johnson",
        "contact_name_parts": {
            "_scheme": "salutation_title_given_family",
            "family_name": "Johnson",
            "given_name": "Cave",
            "salutation": "",
            "title": "Dr"
        },
        "contact_email": "johnson@as.example.org",
        "booth": "A2",
        "locale": "de",
        "access_code": "VKHZ2FU8",
        "allow_lead_scanning": true,
        "allow_lead_access": true,
        "allow_voucher_access": true,
        "comment": ""
      }

   :param organizer: The ``slug`` field of the organizer to create new exhibitor for
   :param event: The ``slug`` field of the event to create new exhibitor for
   :statuscode 201: no error
   :statuscode 400: The exhibitor could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create exhibitors.


.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/exhibitors/(id)/

   Update an exhibitor. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/digitalcontents/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 34

      {
        "internal_id": "ABC"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: text/javascript

      {
        "id": 1,
        "name": "Aperture Science",
        "internal_id": "ABC",
        "contact_name": "Dr Cave Johnson",
        "contact_name_parts": {
            "_scheme": "salutation_title_given_family",
            "family_name": "Johnson",
            "given_name": "Cave",
            "salutation": "",
            "title": "Dr"
        },
        "contact_email": "johnson@as.example.org",
        "booth": "A2",
        "locale": "de",
        "access_code": "VKHZ2FU8",
        "allow_lead_scanning": true,
        "allow_lead_access": true,
        "allow_voucher_access": true,
        "comment": ""
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the exhibitor to modify
   :statuscode 200: no error
   :statuscode 400: The exhibitor could not be modified due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event/exhibitor does not exist **or** you have no permission to change it.


.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/exhibitors/(id)/

   Delete an exhibitor.

   .. warning:: This deletes all lead scan data and deassociates all vouchers (the vouchers are not deleted).

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/exhibitors/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the exhibitor to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event/exhibitor does not exist **or** you have no permission to change it
