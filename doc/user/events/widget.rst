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

.. _Let's Encrypt: https://letsencrypt.org/
