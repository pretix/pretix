.. spelling:word-list:: checkin

Data shredders
==============

pretix and it's plugins include a number of data shredders that allow you to clear personal information from the system.
This page shows you how to use these shredders through the API.

.. warning::

   Unlike the user interface, the API will not force you to download tax-relevant data before you delete it.

Listing available shredders
---------------------------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/shredders/

   Returns a list of all exporters shredders for a given event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/shredders/ HTTP/1.1
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
            "identifier": "question_answers",
            "verbose_name": "Answers to questions"
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

Running an export
-----------------

Before you can delete data, you need to start a data export.
Since exports often include large data sets, they might take longer than the duration of an HTTP request. Therefore,
creating an export is a two-step process. First you need to start an export task with one of the following to API
endpoints:

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/shredders/export/

   Starts an export task. If your input parameters validate correctly, a ``202 Accepted`` status code is returned.
   The body points you to the download URL of the result as well as the URL for the next step.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/shredders/export/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "shredders": ["question_answers"]
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 202 Accepted
      Vary: Accept
      Content-Type: application/json

      {
        "download": "https://pretix.eu/api/v1/organizers/bigevents/events/sampleconf/shredders/download/29891ede-196f-4942-9e26-d055a36e98b8/3f279f13-c198-4137-b49b-9b360ce9fcce/",
        "shred": "https://pretix.eu/api/v1/organizers/bigevents/events/sampleconf/shredders/shred/29891ede-196f-4942-9e26-d055a36e98b8/3f279f13-c198-4137-b49b-9b360ce9fcce/"
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param identifier: The ``identifier`` field of the exporter to run
   :statuscode 202: no error
   :statuscode 400: Invalid input options or event data is not ready to be deleted
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.


Downloading the result
----------------------

When starting an export, you receive a ``download`` URL for downloading the result. Running a ``GET`` request on that result will
yield one of the following status codes:

* ``200 OK`` – The export succeeded. The body will be your resulting file. Might be large!
* ``409 Conflict`` – Your export is still running. The body will be JSON with the structure ``{"status": "running"}``. ``status`` can be ``waiting`` before the task is actually being processed. Please retry, but wait at least one second before you do.
* ``410 Gone`` – Running the export has failed permanently. The body will be JSON with the structure ``{"status": "failed", "message": "Error message"}``
* ``404 Not Found`` – The export does not exist / is expired / belongs to a different API key.


Shredding the data
------------------

When starting an export, you receive a ``shred`` URL for actually shredding the data.
You can only start the actual shredding process after the export file was generated, however you are not forced to download
the file (we'd recommend it in most cases, though).
The download will no longer be possible after the shredding.
Since shredding often requires deleting large data sets, it might take longer than the duration of an HTTP request.
Therefore, shredding again is a two-step process. First you need to start a shredder task with one of the following to API
endpoints:

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/shredders/shred/(id1)/(id2)/

   Starts an export task. If your input parameters validate correctly, a ``202 Accepted`` status code is returned.
   The body points you to an URL you can use to check the status.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/shredders/shred/29891ede-196f-4942-9e26-d055a36e98b8/3f279f13-c198-4137-b49b-9b360ce9fcce/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 202 Accepted
      Vary: Accept
      Content-Type: application/json

      {
        "status": "https://pretix.eu/api/v1/organizers/bigevents/events/sampleconf/shredders/status/29891ede-196f-4942-9e26-d055a36e98b8/3f279f13-c198-4137-b49b-9b360ce9fcce/"
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id1: Opaque value given to you in the previous response
   :param id2: Opaque value given to you in the previous response
   :statuscode 202: no error
   :statuscode 400: Invalid input options
   :statuscode 401: Authentication failure
   :statuscode 404: The export does not exist / is expired / belongs to a different API key.
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 409: Your export is still running. The body will be JSON with the structure ``{"status": "running"}``. ``status`` can be ``waiting`` before the task is actually being processed. Please retry, but wait at least one second before you do.
   :statuscode 410: Either the job has timed out or running the export has failed permanently. The body will be JSON with the structure ``{"status": "failed", "message": "Error message"}``


Checking the result
-------------------

When starting to shred, you receive a ``status`` URL for checking for success.
Running a ``GET`` request on that result will yield one of the following status codes:

* ``200 OK`` – The shredding succeeded.
* ``409 Conflict`` – Shredding is still running. The body will be JSON with the structure ``{"status": "running"}``. ``status`` can be ``waiting`` before the task is actually being processed. Please retry, but wait at least one second before you do.
* ``410 Gone`` – We no longer know about this process, probably the process was started more than an hour ago. Might also occur after successful operations on small pretix installations without asynchronous task handling.
* ``417 Expectation Failed`` – Running the export has failed permanently. The body will be JSON with the structure ``{"status": "failed", "message": "Error message"}``
