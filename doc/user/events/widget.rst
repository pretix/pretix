Embeddable Widget
=================

If you want to show your ticket shop on your event website or blog, you can use our JavaScript widget. This way,
users will not need to leave your site to buy their ticket in most cases. The widget will still open a new tab
for the checkout if the user is on a mobile device.

To obtain the correct HTML code for embedding your event into your website, we recommend that you go to the "Widget"
tab of your event's settings. You can specify some optional settings there (for example the language of the widget)
and then click "Generate widget code".

.. thumbnail:: ../../screens/event/widget_form.png
   :align: center
   :class: screenshot

You will obtain two code snippets that look *roughly* like the following. The first should be embedded into the
``<head>`` part of your website, if possible. If this inconvenient, you can put it in the ``<body>`` part as well::

    <link rel="stylesheet" type="text/css" href="https://pretix.eu/demo/democon/widget/v1.css">
    <script type="text/javascript" src="https://pretix.eu/widget/v1.en.js" async></script>

The second snippet should be embedded at the position where the widget should show up::

    <pretix-widget event="https://pretix.eu/demo/democon/"></pretix-widget>
    <noscript>
       <div class="pretix-widget">
            <div class="pretix-widget-info-message">
                JavaScript is disabled in your browser. To access our ticket shop without JavaScript,
                please <a target="_blank" href="https://pretix.eu/demo/democon/">click here</a>.
            </div>
        </div>
    </noscript>

.. note::

    You can of course embed multiple widgets of multiple events on your page. In this case, please add the first
    snippet only *once* and the second snippets once *for each event*.

.. note::

    Some website builders like Jimdo have trouble with our custom HTML tag. In that case, you can use
    ``<div class="pretix-widget-compat" …></div>`` instead of ``<pretix-widget …></pretix-widget>`` starting with
    pretix 1.14.

Example
-------

Your embedded widget could look like the following:

.. raw:: html

    <link rel="stylesheet" type="text/css" href="https://pretix.eu/demo/democon/widget/v1.css">
    <script type="text/javascript" src="https://pretix.eu/widget/v1.en.js" async></script>
    <pretix-widget event="https://pretix.eu/demo/democon/"></pretix-widget>
    <noscript>
       <div class="pretix-widget">
            <div class="pretix-widget-info-message">
                JavaScript is disabled in your browser. To access our ticket shop without javascript, please <a target="_blank" href="https://pretix.eu/demo/democon/">click here</a>.
            </div>
        </div>
    </noscript>


Styling
-------

If you want, you can customize the appearance of the widget to fit your website with CSS. If you inspect the rendered
HTML of the widget with your browser's developer tools, you will see that nearly every element has a custom class
and all classes are prefixed with ``pretix-widget``. You can override the styles as much as you want to and if
you want to go all custom, you don't even need to use the stylesheet provided by us at all.

SSL
---

Since buying a ticket normally involves entering sensitive data, we strongly suggest that you use SSL/HTTPS for the page
that includes the widget. Initiatives like `Let's Encrypt`_ allow you to obtain a SSL certificate free of charge.

All data transferred to pretix will be made over SSL, even if using the widget on a non-SSL site. However, without
using SSL for your site, a man-in-the-middle attacker could potentially alter the widget in dangerous ways. Moreover,
using SSL is becoming standard practice and your customers might want expect see the secure lock icon in their browser
granted to SSL-enabled web pages.

By default, the checkout process will open in a new tab in your customer's browsers if you don't use SSL for your
website. If you confident to have a good reason for not using SSL, you can override this behavior with the
``skip-ssl-check`` attribute::

   <pretix-widget event="https://pretix.eu/demo/democon/" skip-ssl-check></pretix-widget>

Pre-selecting a voucher
-----------------------

You can pre-select a voucher for the widget with the ``voucher`` attribute::

   <pretix-widget event="https://pretix.eu/demo/democon/" voucher="ABCDE123456"></pretix-widget>

This way, the widget will only show products that can be bought with the voucher and prices according to the
voucher's settings.

.. raw:: html

    <pretix-widget event="https://pretix.eu/demo/democon/" voucher="ABCDE123456"></pretix-widget>
    <noscript>
       <div class="pretix-widget">
            <div class="pretix-widget-info-message">
                JavaScript is disabled in your browser. To access our ticket shop without javascript, please <a target="_blank" href="https://pretix.eu/demo/democon/">click here</a>.
            </div>
        </div>
    </noscript>

Disabling the voucher input
---------------------------

If you want to disable voucher input in the widget, you can pass the ``disable-vouchers`` attribute::

   <pretix-widget event="https://pretix.eu/demo/democon/" disable-vouchers></pretix-widget>

Multi-event selection
---------------------

If you want to embed multiple events in a single widget, you can do so. If it's multiple dates of an event series, just leave off the ``series`` attribute::

   <pretix-widget event="https://pretix.eu/demo/series/"></pretix-widget>

If you want to include all your public events, you can just reference your organizer::

   <pretix-widget event="https://pretix.eu/demo/"></pretix-widget>

There is an optional ``style`` parameter that let's you choose between a calendar view and a list view. If you do not set it, the choice will be taken from your organizer settings::

   <pretix-widget event="https://pretix.eu/demo/series/" style="list"></pretix-widget>
   <pretix-widget event="https://pretix.eu/demo/series/" style="calendar"></pretix-widget>

You can see an example here:

.. raw:: html

    <pretix-widget event="https://pretix.eu/demo/series/" style="calendar"></pretix-widget>
    <noscript>
       <div class="pretix-widget">
            <div class="pretix-widget-info-message">
                JavaScript is disabled in your browser. To access our ticket shop without javascript, please <a target="_blank" href="https://pretix.eu/demo/series/">click here</a>.
            </div>
        </div>
    </noscript>

You can filter events by meta data attributes. You can create those attributes in your order profile and set their values in both event and series date
settings. For example, if you set up a meta data property called "Promoted" that you set to "Yes" on some events, you can pass a filter like this::

   <pretix-widget event="https://pretix.eu/demo/series/" style="list" filter="attr[Promoted]=Yes"></pretix-widget>

pretix Button
-------------

Instead of a product list, you can also display just a single button. When pressed, the button will add a number of
products associated with the button to the cart and will immediately proceed to checkout if the operation succeeded.
You can try out this behavior here:

.. raw:: html

    <pretix-button event="https://pretix.eu/demo/democon/" items="item_6424=1">Buy ticket!</pretix-button>
    <noscript>
       <div class="pretix-widget">
            <div class="pretix-widget-info-message">
                JavaScript is disabled in your browser. To access our ticket shop without javascript, please <a target="_blank" href="https://pretix.eu/demo/democon/">click here</a>.
            </div>
        </div>
    </noscript>
    <br><br>

You can embed the pretix Button just like the pretix Widget. Just like above, first embed the CSS and JavaScript
resources. Then, instead of the ``pretix-widget`` tag, use the ``pretix-button`` tag::

    <pretix-button event="https://pretix.eu/demo/democon/" items="item_6424=1">
        Buy ticket!
    </pretix-button>

As you can see, the ``pretix-button`` element takes an additional ``items`` attribute that specifies the items that
should be added to the cart. The syntax of this attribute is ``item_ITEMID=1,item_ITEMID=2,variation_ITEMID_VARID=4``
where ``ITEMID`` are the internal IDs of items to be added and ``VARID`` are the internal IDs of variations of those
items, if the items have variations. If you omit the ``items`` attribute, the general start page will be presented.

Just as the widget, the button supports the optional attributes ``voucher`` and ``skip-ssl-check``.

You can style the button using the ``pretix-button`` CSS class.

Dynamically loading the widget
------------------------------

If you need to control the way or timing the widget loads, for example because you want to modify user data (see
below) dynamically via JavaScript, you can register a listener that we will call before creating the widget::

    <script type="text/javascript">
    window.pretixWidgetCallback = function () {
        // Will be run before we create the widget.
    }
    </script>

If you want, you can suppress us loading the widget and/or modify the user data passed to the widget::

    <script type="text/javascript">
    window.pretixWidgetCallback = function () {
        window.PretixWidget.build_widgets = false;
        window.PretixWidget.widget_data["email"] = "test@example.org";
    }
    </script>

If you then later want to trigger loading the widgets, just call ``window.PretixWidget.buildWidgets()``.

Waiting for the widget to load
------------------------------

If you want to run custom JavaScript once the widget is fully loaded, you can register a callback function. Note that
this function might be run multiple times, for example if you have multiple widgets on a page or if the user switches
e.g. from an event list to an event detail view::

    <script type="text/javascript">
    window.pretixWidgetCallback = function () {
        window.PretixWidget.addLoadListener(function () {
            console.log("Widget has loaded!");
        });
    }
    </script>


Passing user data to the widget
-------------------------------

If you display the widget in a restricted area of your website and you want to pre-fill fields in the checkout process
with known user data to save your users some typing and increase conversions, you can pass additional data attributes
with that information::

    <pretix-widget event="https://pretix.eu/demo/democon/"
        data-attendee-name-given-name="John"
        data-attendee-name-family-name="Doe"
        data-invoice-address-name-given-name="John"
        data-invoice-address-name-family-name="Doe"
        data-email="test@example.org"
        data-question-L9G8NG9M="Foobar">
    </pretix-widget>

This works for the pretix Button as well. Currently, the following attributes are understood by pretix itself:

* ``data-email`` will pre-fill the order email field as well as the attendee email field (if enabled).

* ``data-question-IDENTIFIER`` will pre-fill the answer for the question with the given identifier. You can view and set
  identifiers in the *Questions* section of the backend.

* Depending on the person name scheme configured in your event settings, you can pass one or more of
  ``data-attendee-name-full-name``, ``data-attendee-name-given-name``, ``data-attendee-name-family-name``,
  ``data-attendee-name-middle-name``, ``data-attendee-name-title``, ``data-attendee-name-calling-name``,
  ``data-attendee-name-latin-transcription``. If you don't know or don't care, you can also just pass a string as
  ``data-attendee-name``, which will pre-fill the last part of the name, whatever that is.

* ``data-invoice-address-FIELD`` will  pre-fill the corresponding field of the invoice address. Possible values for
  ``FIELD`` are ``company``, ``street``, ``zipcode``, ``city`` and ``country``, as well as fields specified by the
  naming scheme such as ``name-title`` or ``name-given-name`` (see above). ``country`` expects a two-character
  country code.

Any configured pretix plugins might understand more data fields. For example, if the appropriate plugins on pretix
Hosted or pretix Enterprise are active, you can pass the following fields:

* If you use the campaigns plugin, you can pass a campaign ID as a value to ``data-campaign``. This way, all orders
  made through this widget will be counted towards this campaign.

* If you use the tracking plugin, you can pass a Google Analytics User ID to enable cross-domain tracking. This will
  require you to dynamically load the widget, like this::

    <script>
        (function(i,s,o,g,r,a,m){i['GoogleAnalyticsObject']=r;i[r]=i[r]||function(){
        (i[r].q=i[r].q||[]).push(arguments)},i[r].l=1*new Date();a=s.createElement(o),
        m=s.getElementsByTagName(o)[0];a.async=1;a.src=g;m.parentNode.insertBefore(a,m)
        })(window,document,'script','https://www.google-analytics.com/analytics.js','ga');

        ga('create', 'UA-XXXXXX-1', 'auto');
        ga('send', 'pageview');

        window.pretixWidgetCallback = function () {
            window.PretixWidget.build_widgets = false;
            window.addEventListener('load', function() { // Wait for GA to be loaded
                if(window.ga && ga.create) {
                    ga(function(tracker) {
                        window.PretixWidget.widget_data["tracking-ga-id"] = tracker.get('clientId');
                        window.PretixWidget.buildWidgets()
                    });
                } else { // Tracking is probably blocked
                       window.PretixWidget.buildWidgets()
                }
            });
        };
    </script>

  In some combinations with Google Tag Manager, the widget does not load this way. In this case, try replacing
  ``tracker.get('clientId')`` with ``ga.getAll()[0].get('clientId')``.


.. versionchanged:: 2.3

   Data passing options have been added in pretix 2.3. If you use a self-hosted version of pretix, they only work
   fully if you configured a redis server.

.. _Let's Encrypt: https://letsencrypt.org/
