.. _`rest-deviceauth`:

Device authentication
=====================

Initializing a new device
-------------------------

Users can create new devices in the "Device" section of their organizer settings. When creating
a new device, users can specify a list of events the device is allowed to access. After a new
device is created, users will be presented initialization instructions, consisting of an URL
and an initialization token. They will also be shown as a QR code with the following contents::

   {"handshake_version": 1, "url": "https://pretix.eu", "token": "kpp4jn8g2ynzonp6"}

Your application should be able to scan a QR code of this type, or allow to enter the URL and the
initialization token manually. The handshake version is not used for manual initialization. When a
QR code is scanned with a higher handshake version than you support, you should reject the request
and prompt the user to update the client application.

After your application received the token, you need to call the initialization endpoint to obtain
a proper API token. At this point, you need to identify the name and version of your application,
as well as the type of underlying hardware. Example:

.. sourcecode:: http

   POST /api/v1/device/initialize HTTP/1.1
   Host: pretix.eu
   Content-Type: application/json

   {
       "token": "kpp4jn8g2ynzonp6",
       "hardware_brand": "Samsung",
       "hardware_model": "Galaxy S",
       "software_brand": "pretixdroid",
       "software_version": "4.0.0"
   }

Every initialization token can only be used once. On success, you will receive a response containing
information on your device as well as your API token:

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/json

   {
       "organizer": "foo",
       "device_id": 5,
       "unique_serial": "HHZ9LW9JWP390VFZ",
       "api_token": "1kcsh572fonm3hawalrncam4l1gktr2rzx25a22l8g9hx108o9oi0rztpcvwnfnd",
       "name": "Bar",
       "gate": {
           "id": 3,
           "name": "South entrance"
       }
   }

Please make sure that you store this ``api_token`` value. We also recommend storing your device ID, your assigned
``unique_serial``, and the ``organizer`` you have access to, but that's up to you. ``gate`` might be ``null``.

In case of an error, the response will look like this:

.. sourcecode:: http

   HTTP/1.1 400 Bad Request
   Content-Type: application/json

   {"token":["This initialization token has already been used."]}


Performing API requests
-----------------------

You need to include the API token with every request to pretix' API in the ``Authorization`` header
like the following:

.. sourcecode:: http
   :emphasize-lines: 3

   GET /api/v1/organizers/ HTTP/1.1
   Host: pretix.eu
   Authorization: Device 1kcsh572fonm3hawalrncam4l1gktr2rzx25a22l8g9hx108o9oi0rztpcvwnfnd

Updating the software version
-----------------------------

If your application is updated, we ask you to tell the server about the new version in use. You can do this at the
following endpoint:

.. sourcecode:: http

   POST /api/v1/device/update HTTP/1.1
   Host: pretix.eu
   Content-Type: application/json
   Authorization: Device 1kcsh572fonm3hawalrncam4l1gktr2rzx25a22l8g9hx108o9oi0rztpcvwnfnd

   {
       "hardware_brand": "Samsung",
       "hardware_model": "Galaxy S",
       "software_brand": "pretixdroid",
       "software_version": "4.1.0"
   }

You will receive a response equivalent to the response of your initialization request.

Creating a new API key
----------------------

If you think your API key might have leaked or just want to be extra cautious, the API allows you to create a new key.
The old API key will be invalid immediately. A request for a new key looks like this:

.. sourcecode:: http

   POST /api/v1/device/roll HTTP/1.1
   Host: pretix.eu
   Authorization: Device 1kcsh572fonm3hawalrncam4l1gktr2rzx25a22l8g9hx108o9oi0rztpcvwnfnd

The response will look like the response to the initialization request.

Removing a device
-----------------

If you want implement a way to to deprovision a device in your software, you can call the ``revoke`` endpoint to
invalidate your API key. There is no way to reverse this operation.

.. sourcecode:: http

   POST /api/v1/device/revoke HTTP/1.1
   Host: pretix.eu
   Authorization: Device 1kcsh572fonm3hawalrncam4l1gktr2rzx25a22l8g9hx108o9oi0rztpcvwnfnd

This can also be done by the user through the web interface.

Permissions & security profiles
-------------------------------

Device authentication is currently hardcoded to grant the following permissions:

* View event meta data and products etc.
* View orders
* Change orders
* Manage gift cards

Devices cannot change events or products and cannot access vouchers.

Additionally, when creating a device through the user interface or API, a user can specify a "security profile" for
the device. These include an allow list of specific API calls that may be made by the device. pretix ships with security
policies for official pretix apps like pretixSCAN and pretixPOS.

Removing a device
-----------------

If you want implement a way to to deprovision a device in your software, you can call the ``revoke`` endpoint to
invalidate your API key. There is no way to reverse this operation.

.. sourcecode:: http

   POST /api/v1/device/revoke HTTP/1.1
   Host: pretix.eu
   Authorization: Device 1kcsh572fonm3hawalrncam4l1gktr2rzx25a22l8g9hx108o9oi0rztpcvwnfnd

This can also be done by the user through the web interface.

Event selection
---------------

In most cases, your application should allow the user to select the event and check-in list they work with manually
from a list. However, in some cases it is required to automatically configure the device for the correct event, for
example in a kiosk-like situation where nobody is operating the device. In this case, the app can query the server
for a suggestion which event should be used. You can also submit the configuration that is currently in use via
query parameters:

.. sourcecode:: http

   GET /api/v1/device/eventselection?current_event=democon&current_subevent=42&current_checkinlist=542 HTTP/1.1
   Host: pretix.eu
   Authorization: Device 1kcsh572fonm3hawalrncam4l1gktr2rzx25a22l8g9hx108o9oi0rztpcvwnfnd

You can get three response codes:

* ``304`` The server things you already selected a good event
* ``404`` The server has not found a suggestion for you
* ``200`` The server suggests a new event (body see below)

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/json

   {
      "event": "democon",
      "subevent": 23,
      "checkinlist": 5
   }

