.. highlight:: python
   :linenothreshold: 5

General APIs
============

This page lists some general signals and hooks which do not belong to a
specific type of plugin but might come in handy for various plugins.

Core
----

.. automodule:: pretix.base.signals
   :members: periodic_task

Order events
""""""""""""

There are multiple signals that will be sent out in the ordering cycle:

.. automodule:: pretix.base.signals
   :members: order_paid, order_placed

Frontend
--------

.. automodule:: pretix.presale.signals
   :members: html_head, footer_links


.. automodule:: pretix.presale.signals
   :members: order_info

Request flow
""""""""""""

.. automodule:: pretix.presale.signals
   :members: process_request, process_response

Vouchers
""""""""

.. automodule:: pretix.presale.signals
   :members: voucher_redeem_info

Backend
-------

.. automodule:: pretix.control.signals
   :members: nav_event, html_head


.. automodule:: pretix.base.signals
   :members: logentry_display

Vouchers
""""""""

.. automodule:: pretix.control.signals
   :members: voucher_form_class, voucher_form_html

Dashboards
""""""""""

.. automodule:: pretix.control.signals
   :members: event_dashboard_widgets, user_dashboard_widgets
