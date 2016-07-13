.. highlight:: python
   :linenothreshold: 5

General APIs
============

This page lists some general signals and hooks which do not belong to a
specific type of plugin but might come in handy for various plugins.

HTML head injection
-------------------

.. automodule:: pretix.control.signals
   :members: html_head

.. automodule:: pretix.presale.signals
   :members: html_head

Admin navigation
----------------

.. automodule:: pretix.control.signals
   :members: nav_event

Footer links
------------

.. automodule:: pretix.presale.signals
   :members: footer_link

Order events
------------

There are multiple signals that will be sent out in the ordering cycle:


.. automodule:: pretix.base.signals
   :members: order_paid, order_placed

Sale flow
---------

.. automodule:: pretix.presale.signals
   :members: order_info

Voucher system
--------------

.. automodule:: pretix.presale.signals
   :members: voucher_redeem_info

.. automodule:: pretix.control.signals
   :members: voucher_form_class, voucher_form_html


Dashboards
----------

.. automodule:: pretix.control.signals
   :members: event_dashboard_widgets, user_dashboard_widgets


Display of log entries
----------------------

.. automodule:: pretix.base.signals
   :members: logentry_display


Periodic tasks
--------------

.. automodule:: pretix.base.signals
   :members: periodic_task
