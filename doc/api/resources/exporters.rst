.. spelling:: checkin

Data exporters
==============

pretix and it's plugins include a number of data exporters that allow you to bulk download various data from pretix in
different formats. This page shows you how to use these exporters through the API.

.. versionchanged:: 3.13

   This feature has been added to the API.

.. warning::

   While we consider the methods listed on this page to be a stable API, the availability and specific input field
   requirements of individual exporters is **not considered a stable API**. Specific exporters and their input parameters
   may change at any time without warning.

Listing available exporters
---------------------------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/exporters/

   Returns a list of all exporters available for a given event. You will receive a list of export methods as well as their
   supported input fields. Note that the exact type and validation requirements of the input fields are not given in the
   response, and you might need to look into the pretix web interface to figure out the exact input required.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/exporters/ HTTP/1.1
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
            "identifier": "orderlist",
            "verbose_name": "Order data",
            "input_parameters": [
              {
                "name": "_format",
                "required": true,
                "choices": [
                  "xlsx",
                  "orders:default",
                  "orders:excel",
                  "orders:semicolon",
                  "positions:default",
                  "positions:excel",
                  "positions:semicolon",
                  "fees:default",
                  "fees:excel",
                  "fees:semicolon"
                ]
              },
              {
                "name": "paid_only",
                "required": false
              }
            ]
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/exporters/

   Returns a list of all cross-event exporters available for a given organizer. You will receive a list of export methods as well as their
   supported input fields. Note that the exact type and validation requirements of the input fields are not given in the
   response, and you might need to look into the pretix web interface to figure out the exact input required.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/exporters/ HTTP/1.1
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
            "identifier": "orderlist",
            "verbose_name": "Order data",
            "input_parameters": [
              {
                "name": "events",
                "required": true
              },
              {
                "name": "_format",
                "required": true,
                "choices": [
                  "xlsx",
                  "orders:default",
                  "orders:excel",
                  "orders:semicolon",
                  "positions:default",
                  "positions:excel",
                  "positions:semicolon",
                  "fees:default",
                  "fees:excel",
                  "fees:semicolon"
                ]
              },
              {
                "name": "paid_only",
                "required": false
              }
            ]
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of the organizer to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

Running an export
-----------------

Since exports often include large data sets, they might take longer than the duration of an HTTP request. Therefore,
creating an export is a two-step process. First you need to start an export task with one of the following to API
endpoints:

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/exporters/(identifier)/run/

   Starts an export task. If your input parameters validate correctly, a ``202 Accepted`` status code is returned.
   The body points you to the download URL of the result.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/exporters/orderlist/run/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "_format": "xlsx"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "download": "https://pretix.eu/api/v1/organizers/bigevents/events/sampleconf/orderlist/download/29891ede-196f-4942-9e26-d055a36e98b8/3f279f13-c198-4137-b49b-9b360ce9fcce/"
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param identifier: The ``identifier`` field of the exporter to run
   :statuscode 202: no error
   :statuscode 400: Invalid input options
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/exporters/(identifier)/run/

   The endpoint for organizer-level exports works just like event-level exports (see above).


Downloading the result
----------------------

When starting an export, you receive a ``url`` for downloading the result. Running a ``GET`` request on that result will
yield one of the following status codes:

* ``200 OK`` – The export succeeded. The body will be your resulting file. Might be large!
* ``409 Conflict`` – Your export is still running. The body will be JSON with the structure ``{"status": "running", "percentage": 40}``. ``percentage`` can be ``null`` if it is not known and ``status`` can be ``waiting`` before the task is actually being processed. Please retry, but wait at least one second before you do.
* ``410 Gone`` – Running the export has failed permanently. The body will be JSON with the structure ``{"status": "failed", "message": "Error message"}``
* ``404 Not Found`` – The export does not exist / is expired.

.. warning::

   Running exports puts a lot of stress on the system, we kindly ask you not to run more than two exports at the same time.

