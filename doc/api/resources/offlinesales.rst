Offline sales
=============

.. note:: This API is only available when the plugin **pretix-offlinesales** is installed (pretix Hosted and Enterprise only).

The offline sales module allows you to create batches of tickets intended for the sale outside the system.

Resource description
--------------------

The offline sales batch resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal batch ID
creation                              datetime                   Time of creation
testmode                              boolean                    ``true`` if orders are created in test mode
sales_channel                         string                     Sales channel of the orders
layout                                integer                    Internal ID of the chosen ticket layout
subevent                              integer                    Internal ID of the chosen subevent (or ``null``)
item                                  integer                    Internal ID of the chosen product
variation                             integer                    Internal ID of the chosen variation (or ``null``)
amount                                integer                    Number of tickets in the batch
comment                               string                     Internal comment
orders                                list of strings            List of order codes (omitted in list view for performance reasons)
===================================== ========================== =======================================================

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/offlinesalesbatches/

   Returns a list of all offline sales batches

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/democon/offlinesalesbatches/ HTTP/1.1
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
            "creation": "2025-07-08T18:27:32.134368+02:00",
            "testmode": False,
            "sales_channel": "web",
            "comment": "Batch for sale at the event",
            "layout": 3,
            "subevent": null,
            "item": 23,
            "variation": null,
            "amount": 7
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of a valid event
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/offlinesalesbatches/(id)/

   Returns information on a given batch.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/democon/offlinesalesbatches/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: text/javascript

      {
        "id": 1,
        "creation": "2025-07-08T18:27:32.134368+02:00",
        "testmode": False,
        "sales_channel": "web",
        "comment": "Batch for sale at the event",
        "layout": 3,
        "subevent": null,
        "item": 23,
        "variation": null,
        "amount": 7,
        "orders": ["TSRNN", "3FBSL", "WMDNJ", "BHW9H", "MXSUG", "DSDAP", "URLLE"]
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the batch to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view it.


.. http:post:: /api/v1/organizers/(organizer)/events/(event)/offlinesalesbatches/

   With this API call, you can instruct the system to create a new batch.

   Since batches can contain up to 10,000 tickets, they are created asynchronously on the server.
   If your input parameters validate correctly, a ``202 Accepted`` status code is returned.
   The body points you to the check URL of the result. Running a ``GET`` request on that result URL will
   yield one of the following status codes:

    * ``200 OK`` – The creation of the batch has succeeded. The body will be your resulting batch with the same information as in the detail endpoint above.
    * ``409 Conflict`` – Your creation job is still running. The body will be JSON with the structure ``{"status": "running"}``. ``status`` can be ``waiting`` before the task is actually being processed. Please retry, but wait at least one second before you do.
    * ``410 Gone`` – Creating the batch has failed permanently (e.g. quota no longer available). The body will be JSON with the structure ``{"status": "failed", "message": "Error message"}``
    * ``404 Not Found`` – The job does not exist / is expired.

   .. note:: To avoid performance issues, a maximum amount of 10000 is currently allowed.

   .. note:: Do not wait multiple hours or more to retrieve your result. After a longer wait time, ``409`` might be returned permanently due to technical constraints, even though nothing will happen any more.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/offlinesalesbatches/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "testmode": True,
        "layout": 123,
        "item": 14,
        "sales_channel": "web",
        "amount": 10,
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "check": "https://pretix.eu/api/v1/organizers/bigevents/events/sampleconf/offlinesalesbatches/check/29891ede-196f-4942-9e26-d055a36e98b8/"
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :statuscode 202: no error
   :statuscode 400: Invalid input options
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.


.. http:post:: /api/v1/organizers/(organizer)/events/(event)/offlinesalesbatches/(id)/render/

   With this API call, you can render the PDF representation of a batch.

   Since batches can contain up to 10,000 tickets, they are rendered asynchronously on the server.
   If your input parameters validate correctly, a ``202 Accepted`` status code is returned.
   The body points you to the download URL of the result. Running a ``GET`` request on that result URL will
   yield one of the following status codes:

    * ``200 OK`` – The creation of the batch has succeeded. The body will be your resulting batch with the same information as in the detail endpoint above.
    * ``409 Conflict`` – Your rendering process is still running. The body will be JSON with the structure ``{"status": "running"}``. ``status`` can be ``waiting`` before the task is actually being processed. Please retry, but wait at least one second before you do.
    * ``410 Gone`` – Rendering the batch has failed permanently. The body will be JSON with the structure ``{"status": "failed", "message": "Error message"}``
    * ``404 Not Found`` – The rendering job does not exist / is expired.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/offlinesalesbatches/1/render HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "download": "https://pretix.eu/api/v1/organizers/bigevents/events/sampleconf/offlinesalesbatches/1/download/29891ede-196f-4942-9e26-d055a36e98b8/3f279f13-c198-4137-b49b-9b360ce9fcce/"
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the batch to fetch
   :statuscode 202: no error
   :statuscode 400: Invalid input options
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

