.. highlight:: python
   :linenothreshold: 5

General APIs
============

This page lists some general signals and hooks which do not belong to a
specific type of plugin but might come in handy for various plugins.

Core
----

.. automodule:: pretix.base.signals
   :members: periodic_task, event_live_issues, event_copy_data, email_filter, register_notification_types,
      item_copy_data, register_sales_channels

Order events
""""""""""""

There are multiple signals that will be sent out in the ordering cycle:

.. automodule:: pretix.base.signals
   :members: validate_cart, order_fee_calculation, order_paid, order_placed, order_canceled, order_expired, order_modified, order_changed, order_approved, order_denied, order_fee_type_name, allow_ticket_download

Frontend
--------

.. automodule:: pretix.presale.signals
   :members: html_head, html_footer, footer_link, front_page_top, front_page_bottom, fee_calculation_for_cart, contact_form_fields, question_form_fields, checkout_confirm_messages, checkout_confirm_page_content, checkout_all_optional, html_page_header, sass_preamble, sass_postamble


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
   :members: nav_event, html_head, html_page_start, quota_detail_html, nav_topbar, nav_global, nav_organizer, nav_event_settings,
             order_info, event_settings_widget, oauth_application_registered, order_position_buttons


.. automodule:: pretix.base.signals
   :members: logentry_display, logentry_object_link, requiredaction_display

Vouchers
""""""""

.. automodule:: pretix.control.signals
   :members: item_forms

Vouchers
""""""""

.. automodule:: pretix.control.signals
   :members: voucher_form_class, voucher_form_html, voucher_form_validation

Dashboards
""""""""""

.. automodule:: pretix.control.signals
   :members: event_dashboard_widgets, user_dashboard_widgets

Ticket designs
""""""""""""""

.. automodule:: pretix.base.signals
   :members: layout_text_variables
