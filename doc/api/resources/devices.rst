.. spelling:: fullname

.. _`rest-devices`:

Devices
=======

See also :ref:`rest-deviceauth`.

Device resource
----------------

The device resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
device_id                             integer                    Internal ID of the device within this organizer
unique_serial                         string                     Unique identifier of this device
name                                  string                     Device name
all_events                            boolean                    Whether this device has access to all events
limit_events                          list                       List of event slugs this device has access to
hardware_brand                        string                     Device hardware manufacturer (read-only)
hardware_model                        string                     Device hardware model (read-only)
software_brand                        string                     Device software product (read-only)
software_version                      string                     Device software version (read-only)
created                               datetime                   Creation time
initialized                           datetime                   Time of initialization (or ``null``)
initialization_token                  string                     Token for initialization
revoked                               boolean                    Whether this device no longer has access
security_profile                      string                     The name of a supported security profile restricting API access
===================================== ========================== =======================================================

Device endpoints
----------------

.. http:get:: /api/v1/organizers/(organizer)/devices/

   Returns a list of all devices within a given organizer.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/devices/ HTTP/1.1
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
            "device_id": 1,
            "unique_serial": "UOS3GNZ27O39V3QS",
            "initialization_token": "frkso3m2w58zuw70",
            "all_events": false,
            "limit_events": [
              "museum"
            ],
            "revoked": false,
            "name": "Scanner",
            "created": "2020-09-18T14:17:40.971519Z",
            "initialized": "2020-09-18T14:17:44.190021Z",
            "security_profile": "full",
            "hardware_brand": "Zebra",
            "hardware_model": "TC25",
            "software_brand": "pretixSCAN",
            "software_version": "1.5.1"
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of the organizer to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/devices/(device_id)/

   Returns information on one device, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/devices/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "device_id": 1,
        "unique_serial": "UOS3GNZ27O39V3QS",
        "initialization_token": "frkso3m2w58zuw70",
        "all_events": false,
        "limit_events": [
          "museum"
        ],
        "revoked": false,
        "name": "Scanner",
        "created": "2020-09-18T14:17:40.971519Z",
        "initialized": "2020-09-18T14:17:44.190021Z",
        "security_profile": "full",
        "hardware_brand": "Zebra",
        "hardware_model": "TC25",
        "software_brand": "pretixSCAN",
        "software_version": "1.5.1"
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param device_id: The ``device_id`` field of the device to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/devices/

   Creates a new device

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/devices/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "name": "Scanner",
        "all_events": true,
        "limit_events": [],
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "device_id": 1,
        "unique_serial": "UOS3GNZ27O39V3QS",
        "initialization_token": "frkso3m2w58zuw70",
        "all_events": true,
        "limit_events": [],
        "revoked": false,
        "name": "Scanner",
        "created": "2020-09-18T14:17:40.971519Z",
        "security_profile": "full",
        "initialized": null
        "hardware_brand": null,
        "hardware_model": null,
        "software_brand": null,
        "software_version": null
      }

   :param organizer: The ``slug`` field of the organizer to create a device for
   :statuscode 201: no error
   :statuscode 400: The device could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/devices/(device_id)/

   Update a device.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/devices/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "name": "Foo"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "name": "Foo",
        ...
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param device_id: The ``device_id`` field of the device to modify
   :statuscode 200: no error
   :statuscode 400: The device could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to change this resource.

