Ticket settings
===============

At "Settings" → "Tickets", you can configure the ticket download options that will be presented to your customers:

.. thumbnail:: ../../screens/event/settings_tickets.png
   :align: center
   :class: screenshot

The top of this page shows a short list of options relevant for all download formats:

Use feature
  This can be used to completely enable or disable ticket downloads all over your ticket shop.

Download date
  If you set a date here, no ticket download will be offered before this date. If no date is set, tickets can be
  downloaded immediately after the payment for an order has been received.

Offer to download tickets separately for add-on products
  By default, tickets can not be downloaded for order positions which are only an add-on to other order positions. If
  you enable this, this behavior will be changed and add-on products will get their own tickets as well. If disabled,
  you can still print a list of chosen add-ons e.g. on the PDF tickets.

Generate tickets for non-admission products
  By default, tickets will only be generated for products that are marked as admission products. Enable this option to
  generate tickets for all products instead.

Offer to download tickets even before an order is paid
  By default, ticket download is only possible for paid orders. If you run an event where people usually pay only after
  the event, you can check this box to enable ticket download even before.

Below these settings, the detail settings for the various ticket file formats are offered. They differ from format to
format and only share the common "Enable" setting that can be used to turn them on. By default, pretix ships with
a PDF output plugin that you can configure through a visual design editor.