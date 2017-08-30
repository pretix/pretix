.. highlight:: python
   :linenothreshold: 5

General APIs
============

This page lists some general signals and hooks which do not belong to a
specific type of plugin but might come in handy for various plugins.

Core
----

.. automodule:: pretix.base.signals
   :members: periodic_task, event_live_issues, event_copy_data

Order events
""""""""""""

There are multiple signals that will be sent out in the ordering cycle:

.. automodule:: pretix.base.signals
   :members: validate_cart, order_paid, order_placed

Frontend
--------

.. automodule:: pretix.presale.signals
   :members: html_head, html_footer, footer_links, front_page_top, front_page_bottom, contact_form_fields, question_form_fields, checkout_confirm_messages


.. automodule:: pretix.presale.signals
   :members: order_info, order_meta_from_request

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
   :members: nav_event, html_head, quota_detail_html, nav_topbar, nav_global, nav_organizer


.. automodule:: pretix.base.signals
   :members: logentry_display, requiredaction_display

Vouchers
""""""""

.. automodule:: pretix.control.signals
   :members: voucher_form_class, voucher_form_html, voucher_form_validation

Dashboards
""""""""""

.. automodule:: pretix.control.signals
   :members: event_dashboard_widgets, user_dashboard_widgets
