.. _`webhooks`:

Webhooks
========

pretix can send webhook calls to notify your application of any changes that happen inside pretix. This is especially
useful for everything triggered by an actual user, such as a new ticket sale or the arrival of a payment.

You can register any number of webhook URLs that pretix will notify any time one of the supported events occurs inside
your organizer account. A great example use case of webhooks would be to add the buyer to your mailing list every time
a new order comes in.

Configuring webhooks
--------------------

You can find the list of your active webhooks in the "Webhook" section of your organizer account:

.. thumbnail:: ../screens/organizer/webhook_list.png
   :align: center
   :class: screenshot

Click "Create webhook" if you want to add a new URL. You will then be able to enter the URL pretix shall call for
notifications. You need to select any number of notification types that you want to receive and you can optionally
filter the events you want to receive notifications for.

.. thumbnail:: ../screens/organizer/webhook_edit.png
   :align: center
   :class: screenshot

You can also configure webhooks :ref:`through the API itself <rest-webhooks>`.

Receiving webhooks
------------------

Creating a webhook endpoint on your server is no different from creating any other page on your website. If your
website is written in PHP, you might just create a new ``.php`` file on your server; if you use a web framework like
Symfony or Django, you would just create a new route with the desired URL.

We will call your URL with a HTTP ``POST`` request with a ``JSON`` body. In PHP, you can parse this like this::

    $input = @file_get_contents('php://input');
    $event_json = json_decode($input);
    // Do something with $event_json

In Django, you would create a view like this::

    def my_webhook_view(request):
      event_json = json.loads(request.body)
      # Do something with event_json
      return HttpResponse(status=200)

More samples for the language of your choice are easy to find online.

The exact body of the request varies by notification type, but for the main types included with pretix core, such as
those related to changes of an order, it will look like this::

    {
      "notification_id": 123455,
      "organizer": "acmecorp",
      "event": "democon",
      "code": "ABC23",
      "action": "pretix.event.order.placed"
    }

Notifications regarding a check-in will contain more details like ``orderposition_id``
and ``checkin_list``.

.. warning:: You should not trust data supplied to your webhook, but only use it as a trigger to fetch updated data.
             Anyone could send data there if they guess the correct URL and you won't be able to tell. Therefore, we
             only include the minimum amount of data necessary for you to fetch the changed objects from our
             :ref:`rest-api` in an authenticated way.

If you want to further prevent others from accessing your webhook URL, you can also use `Basic authentication`_ and
supply the URL to us in the format of ``https://username:password@domain.com/path/``.
We recommend that you use HTTPS for your webhook URL and might require it in the future. If HTTPS is used, we require
that a valid certificate is in use.

.. note:: If you use a web framework that makes use of automatic CSRF protection, this protection might prevent us
          from calling your webhook URL. In this case, we recommend that you turn of CSRF protection selectively
          for that route. In Django, you can do this by putting the ``@csrf_exempt`` decorator on your view. In
          Rails, you can pass an ``except`` parameter to ``protect_from_forgery``.


Responding to a webhook
-----------------------

If you successfully received a webhook call, your endpoint should return a HTTP status code between ``200`` and ``299``.
If any other status code is returned, we will assume you did not receive the call. This does mean that any redirection
or ``304 Not Modified`` response will be treated as a failure. pretix will not follow any ``301`` or ``302`` redirect
headers and pretix will ignore all other information in your response headers or body.

If we do not receive a status code in the range of ``200`` and ``299``, pretix will retry to deliver for up to three
days with an exponential back off. Therefore, we recommend that you implement your endpoint in a way where calling it
multiple times for the same event due to a perceived error does not do any harm.

There is only one exception: If status code ``410 Gone`` is returned, we will assume the
endpoint does not exist any more and automatically disable the webhook.

.. note:: If you use a self-hosted version of pretix (i.e. not our SaaS offering at pretix.eu) and you did not
          configure a background task queue, failed webhooks will not be retried.

Debugging webhooks
------------------

If you want to debug your webhooks, you can view a log of all sent notifications and the responses of your server for
30 days right next to your configuration.

.. _Basic authentication: https://en.wikipedia.org/wiki/Basic_access_authentication
