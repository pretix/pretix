.. _`rest-tokenauth`:

Token-based authentication
==========================

Obtaining an API token
----------------------

To authenticate your API requests with Tokens, you need to obtain a team-level API token.
You can create a token in the pretix web interface on the level of organizer teams. Create
a new team or choose an existing team that has the level of permissions the token should
have and create a new token using the form below the list of team members:

.. image:: img/token_form.png
   :class: screenshot

You can enter a description for the token to distinguish from other tokens later on.
Once you click "Add", you will be provided with an API token in the success message.
Copy this token, as you won't be able to retrieve it again.

.. image:: img/token_success.png
   :class: screenshot

Using an API token
------------------

You need to include the API token with every request to pretix' API in the ``Authorization`` header
like the following:

.. sourcecode:: http
   :emphasize-lines: 3

   GET /api/v1/organizers/ HTTP/1.1
   Host: pretix.eu
   Authorization: Token e1l6gq2ye72thbwkacj7jbri7a7tvxe614ojv8ybureain92ocub46t5gab5966k

