Exhibitors
==========

.. note:: This API is only available when the plugin **pretix-exhibitors** is installed (pretix Hosted and Enterprise only).

The exhibitors plugin allows to manage exhibitors at your trade show or conference. After signing up your exhibitors
in the system, you can assign vouchers to exhibitors and give them access to the data of these vouchers. The exhibitors
module is also the basis of the pretixLEAD lead scanning application.

.. note:: On pretix Hosted, using the lead scanning feature of the exhibitors plugin can add additional costs
          depending on your contract.

The plugin exposes two APIs. One (REST API) is intended for bulk-data operations from the admin side, and one
(App API) that is used by the pretixLEAD app.

REST API
---------

The REST API for exhibitors requires the usual :ref:`rest-auth`.

Resources
"""""""""

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
contact_cc_email                      string                     Copy email addresses, can be multiple separated by comma (or ``null``)
booth                                 string                     Booth number (or ``null``). Maximum 100 characters.
locale                                string                     Locale for communication with the exhibitor.
access_code                           string                     Access code for the exhibitor to access their data or use the lead scanning app (read-only).
lead_scanning_access_code             string                     Access code for the exhibitor to use the lead scanning app but not access data (read-only).
allow_lead_scanning                   boolean                    Enables lead scanning app
allow_lead_access                     boolean                    Enables access to data gathered by the lead scanning app
allow_voucher_access                  boolean                    Enables access to data gathered by exhibitor vouchers
lead_scanning_scope_by_device         string                     Enables lead scanning to be handled as one lead per attendee
                                                                 per scanning device, instead of only per exhibitor.
comment                               string                     Internal comment, not shown to exhibitor
exhibitor_tags                        list of strings            Internal tags to categorize exhibitors, not shown to exhibitor.
                                                                 The tags need to be created through the web interface currently.
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
data                                  list of objects            Attendee data set that may be shown to the exhibitor based o
                                                                 the event's configuration. Each entry contains the fields ``id``,
                                                                 ``label``, ``value``, and ``details``. ``details`` is usually empty
                                                                 except in a few cases where it contains an additional list of objects
                                                                 with ``value`` and ``label`` keys (e.g. splitting of names).
device_name                           string                     User-defined name for the device used for scanning (or ``null``).
device_uuid                           string                     UUID of device used for scanning (or ``null``).
===================================== ========================== =======================================================

Endpoints
"""""""""

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
            "contact_cc_email": "miller@as.example.org,smith@as.example.org",
            "booth": "A2",
            "locale": "de",
            "access_code": "VKHZ2FU84",
            "lead_scanning_access_code": "WVK2B8PZ",
            "lead_scanning_scope_by_device": false,
            "allow_lead_scanning": true,
            "allow_lead_access": true,
            "allow_voucher_access": true,
            "comment": "",
            "exhibitor_tags": []
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
        "contact_cc_email": "miller@as.example.org,smith@as.example.org",
        "booth": "A2",
        "locale": "de",
        "access_code": "VKHZ2FU84",
        "lead_scanning_access_code": "WVK2B8PZ",
        "lead_scanning_scope_by_device": false,
        "allow_lead_scanning": true,
        "allow_lead_access": true,
        "allow_voucher_access": true,
        "comment": "",
        "exhibitor_tags": []
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
            "first_upload": "2021-07-06T11:03:31.414491+01:00",
            "data": [
              {
                "id": "attendee_name",
                "label": "Attendee name",
                "value": "Peter Miller",
                "details": [
                  {"label": "Given name", "value": "Peter"},
                  {"label": "Family name", "value": "Miller"},
                ]
              }
            ]
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

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/exhibitors/(id)/vouchers/

   Returns a list of all vouchers connected to an exhibitor. The response contains the same data as described in
   :ref:`rest-vouchers` as well as for each voucher an additional field ``exhibitor_comment`` that is shown to the exhibitor. It can only
   be modified using the ``attach`` API call below.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/exhibitors/1/vouchers/ HTTP/1.1
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
            "code": "43K6LKM37FBVR2YG",
            "max_usages": 1,
            "redeemed": 0,
            "valid_until": null,
            "block_quota": false,
            "allow_ignore_quota": false,
            "price_mode": "set",
            "value": "12.00",
            "item": 1,
            "variation": null,
            "quota": null,
            "tag": "testvoucher",
            "comment": "",
            "seat": null,
            "subevent": null
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

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/exhibitors/(id)/vouchers/attach/

   Attaches an **existing** voucher to an exhibitor. You need to send either the ``id`` **or** the ``code`` field of
   the voucher. You can call this method multiple times to update the optional ``exhibitor_comment`` field.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/exhibitors/1/vouchers/attach/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

     {
       "id": 15,
       "exhibitor_comment": "Free ticket"
     }

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/exhibitors/1/vouchers/attach/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

     {
       "code": "43K6LKM37FBVR2YG",
       "exhibitor_comment": "Free ticket"
     }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {}

   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of the event to use
   :param id: The ``id`` field of the exhibitor to use
   :statuscode 200: no error
   :statuscode 400: Invalid data sent, e.g. voucher does not exist
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or event or exhibitor does not exist **or** you have no permission to view it.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/exhibitors/(id)/vouchers/bulk_attach/

   Attaches many **existing** vouchers to an exhibitor. You need to send either the ``id`` **or** the ``code`` field of
   the voucher, but you need to send the same field for all entries.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/exhibitors/1/vouchers/bulk_attach/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

     [
       {
         "id": 15,
         "exhibitor_comment": "Free ticket"
       },
       ..
     ]

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {}

   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of the event to use
   :param id: The ``id`` field of the exhibitor to use
   :statuscode 200: no error
   :statuscode 400: Invalid data sent, e.g. voucher does not exist
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
        "contact_cc_email": "miller@as.example.org,smith@as.example.org",
        "booth": "A2",
        "locale": "de",
        "allow_lead_scanning": true,
        "allow_lead_access": true,
        "allow_voucher_access": true,
        "comment": "",
        "exhibitor_tags": [
          "Gold Sponsor"
        ]
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
        "contact_cc_email": "miller@as.example.org,smith@as.example.org",
        "booth": "A2",
        "locale": "de",
        "access_code": "VKHZ2FU84",
        "lead_scanning_access_code": "WVK2B8PZ",
        "lead_scanning_scope_by_device": false,
        "allow_lead_scanning": true,
        "allow_lead_access": true,
        "allow_voucher_access": true,
        "comment": "",
        "exhibitor_tags": [
          "Gold Sponsor"
        ]
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

      PATCH /api/v1/organizers/bigevents/events/sampleconf/exhibitors/1/ HTTP/1.1
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
        "contact_cc_email": "miller@as.example.org,smith@as.example.org",
        "booth": "A2",
        "locale": "de",
        "access_code": "VKHZ2FU84",
        "lead_scanning_access_code": "WVK2B8PZ",
        "lead_scanning_scope_by_device": false,
        "allow_lead_scanning": true,
        "allow_lead_access": true,
        "allow_voucher_access": true,
        "comment": "",
        "exhibitor_tags": [
          "Gold Sponsor"
        ]
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the exhibitor to modify
   :statuscode 200: no error
   :statuscode 400: The exhibitor could not be modified due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event/exhibitor does not exist **or** you have no permission to change it.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/exhibitors/(id)/send_access_code/

   Sends an email to the exhibitor with their access code.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/exhibitors/1/send_access_code/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript


   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param code: The ``id`` field of the exhibitor to send an email for
   :statuscode 200: no error
   :statuscode 400: The exhibitor does not have an email address associated
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested exhibitor does not exist.
   :statuscode 503: The email could not be sent.


.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/exhibitors/(id)/

   Delete an exhibitor.

   .. warning:: This deletes all lead scan data and removes all connections to vouchers (the vouchers are not deleted).

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


App API
-------

The App API is used for communication between the pretixLEAD app and the pretix server.

.. warning:: We consider this an internal API, it is not intended for external use. You may still use it, but
             our :ref:`compatibility commitment <rest-compat>` does not apply.

Authentication
""""""""""""""

Every exhibitor has an "access code", usually consisting of 8 alphanumeric uppercase characters.
This access code is communicated to event exhibitors by the event organizers, so this is also what
exhibitors should enter into a login screen.

All API requests need to contain this access code as a header like this::

    Authorization: Exhibitor ABCDE123

Exhibitor profile
"""""""""""""""""

Upon login and in regular intervals after that, the API should fetch the exhibitors profile.
This serves two purposes:

* Checking if the authorization code is actually valid

* Obtaining information that can be shown in the app

The resource consists of the following fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
name                                  string                     Exhibitor name
booth                                 string                     Booth number (or ``null``)
event                                 object                     Object describing the event
├ name                                multi-lingual string       Event name
├ end_date                            datetime                   End date of the event. After this time, the app could show a warning that the event is over.
├ imprint_url                         string                     URL to legal notice page. If not ``null``, a button in the app should link to this page.
├ privacy_url                         string                     URL to privacy notice page. If not ``null``, a button in the app should link to this page.
├ help_url                            string                     URL to help page. If not ``null``, a button in the app should link to this page.
├ terms_url                           string                     URL to terms of service. If not ``null``, a button in the app should link to this page.
├ logo_url                            string                     URL to event logo. If not ``null``, this logo may be shown in the app.
├ slug                                string                     Event short form
└ organizer                           string                     Organizer short form
notes                                 boolean                    Specifies whether the exhibitor is allowed to take notes on leads
tags                                  list of strings            List of tags the exhibitor can assign to their leads
scan_types                            list of objects            Only used for a special case, fixed value that external API consumers should ignore
===================================== ========================== =======================================================

.. http:get:: /exhibitors/api/v1/profile

   **Example request:**

   .. sourcecode:: http

    GET /exhibitors/api/v1/profile HTTP/1.1
    Authorization: Exhibitor ABCDE123
    Accept: application/json, text/javascript

   **Example response:**

   .. sourcecode:: http

    HTTP/1.1 200 OK
    Vary: Accept
    Content-Type: application/json

    {
      "name": "Aperture Science",
      "booth": "A2",
      "event": {
        "name": {"en": "Sample conference", "de": "Beispielkonferenz"},
        "end_date": "2017-12-28T10:00:00+00:00",
        "slug": "bigevents",
        "imprint_url": null,
        "privacy_url": null,
        "help_url": null,
        "terms_url": null,
        "logo_url": null,
        "organizer": "sampleconf"
      },
      "notes": true,
      "tags": ["foo", "bar"],
      "scan_types": [
        {
          "key": "lead",
          "label": "Lead Scanning"
        }
      ]
    }

   :statuscode 200: no error
   :statuscode 401: Invalid authentication code

Submitting a lead
"""""""""""""""""

After a ticket/badge is scanned, it should immediately be submitted to the server
so the scan is stored and information about the person can be shown in the app. The same
code can be submitted multiple times, so it's no problem to just submit it again after the
exhibitor set a note or a rating (0-5) inside the app.

On the request, you should set the following properties:

* ``code`` with the scanned barcode
* ``notes`` with the exhibitor's notes
* ``scanned`` with the date and time of the actual scan (not the time of the upload)
* ``scan_type`` set to ``lead`` statically
* ``tags`` with the list of selected tags
* ``rating`` with the rating assigned by the exhibitor
* ``device_name`` with a user-specified name of the device used for scanning (max. 190 characters), or ``null``
* ``device_uuid`` with a auto-generated UUID of the device used for scanning, or ``null``

If you submit ``tags`` and ``rating`` to be ``null`` and ``notes`` to be ``""``, the server
responds with the previously saved information and will not delete that information. If you
supply other values, the information saved on the server will be overridden.

The response will also contain ``tags``, ``rating``, and ``notes``. Additionally,
it will include ``attendee`` with a list of ``fields`` that can be shown to the
user. Each field has an internal ``id``, a human-readable ``label``, and a ``value`` (all strings).

Note that the ``fields`` array can contain any number of dynamic keys!
Depending on the exhibitors permission and event configuration this might be empty,
or contain lots of details. The app should dynamically show these values (read-only)
with the labels sent by the server.

The request for this looks like this:

.. http:post:: /exhibitors/api/v1/leads/

   **Example request:**

   .. sourcecode:: http

    POST /exhibitors/api/v1/leads/ HTTP/1.1
    Authorization: Exhibitor ABCDE123
    Accept: application/json, text/javascript
    Content-Type: application/json

    {
      "code": "qrcodecontent",
      "notes": "Great customer, wants our newsletter",
      "scanned": "2020-10-18T12:24:23.000+00:00",
      "scan_type": "lead",
      "tags": ["foo"],
      "rating": 4,
      "device_name": "DEV1",
      "device_uuid": "d8c2ec53-d602-4a08-882d-db4cf54344a2"
    }

   **Example response:**

   .. sourcecode:: http

    HTTP/1.1 201 Created
    Vary: Accept
    Content-Type: application/json

    {
      "attendee": {
        "fields": [
          {
            "id": "attendee_name",
            "label": "Name",
            "value": "Jon Doe",
            "details": [
              {"label": "Given name", "value": "John"},
              {"label": "Family name", "value": "Doe"},
            ]
          },
          {
            "id": "attendee_email",
            "label": "Email",
            "value": "test@example.com",
            "details": []
          }
         ]
        },
        "rating": 4,
        "tags": ["foo"],
        "notes": "Great customer, wants our newsletter",
        "device_name": "DEV1",
        "device_uuid": "d8c2ec53-d602-4a08-882d-db4cf54344a2"
    }

   :statuscode 200: No error, leads was not scanned for the first time
   :statuscode 201: No error, leads was scanned for the first time
   :statuscode 400: Invalid data submitted
   :statuscode 401: Invalid authentication code

You can also fetch existing leads (if you are authorized to do so):

.. http:get:: /exhibitors/api/v1/leads/

   **Example request:**

   .. sourcecode:: http

    GET /exhibitors/api/v1/leads/ HTTP/1.1
    Authorization: Exhibitor ABCDE123
    Accept: application/json, text/javascript

   **Example response:**

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
          "attendee": {
            "fields": [
              {
                "id": "attendee_name",
                "label": "Name",
                "value": "Jon Doe",
                "details": [
                  {"label": "Given name", "value": "John"},
                  {"label": "Family name", "value": "Doe"},
                ]
              },
              {
                "id": "attendee_email",
                "label": "Email",
                "value": "test@example.com",
                "details": []
              }
           ]
          },
          "rating": 4,
          "tags": ["foo"],
          "notes": "Great customer, wants our newsletter",
          "device_name": "DEV1",
          "device_uuid": "d8c2ec53-d602-4a08-882d-db4cf54344a2"
        }
      ]
    }

   :statuscode 200: No error
   :statuscode 401: Invalid authentication code
   :statuscode 403: Not permitted to access bulk data
