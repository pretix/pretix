#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Jakob Schnell, Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from django.dispatch import Signal

from pretix.base.signals import EventPluginSignal

global_html_head = Signal()
"""
Arguments: ``request``

This signal allows you to put code inside the HTML ``<head>`` tag
of every page in the frontend. You will get the request as the keyword argument
``request`` and are expected to return plain HTML.

This signal is called regardless of whether your plugin is active for all pages of the system.
"""

global_html_page_header = Signal()
"""
Arguments: ``request``

This signal allows you to put code right in the beginning of the HTML ``<body>`` tag
of every page in the frontend. You will get the request as the keyword argument
``request`` and are expected to return plain HTML.

This signal is called regardless of whether your plugin is active for all pages of the system.
"""

global_html_footer = Signal()
"""
Arguments: ``request``

This signal allows you to put code before the end of the HTML ``<body>`` tag
of every page in the frontend. You will get the request as the keyword argument
``request`` and are expected to return plain HTML.

This signal is called regardless of whether your plugin is active for all pages of the system.
"""

html_head = EventPluginSignal()
"""
Arguments: ``request``

This signal allows you to put code inside the HTML ``<head>`` tag
of every page in the frontend. You will get the request as the keyword argument
``request`` and are expected to return plain HTML.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

html_page_header = EventPluginSignal()
"""
Arguments: ``request``

This signal allows you to put code right in the beginning of the HTML ``<body>`` tag
of every page in the frontend. You will get the request as the keyword argument
``request`` and are expected to return plain HTML.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

html_footer = EventPluginSignal()
"""
Arguments: ``request``

This signal allows you to put code before the end of the HTML ``<body>`` tag
of every page in the frontend. You will get the request as the keyword argument
``request`` and are expected to return plain HTML.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

sass_preamble = EventPluginSignal()
"""
Arguments: ``filename``

This signal allows you to put SASS code at the beginning of the event-specific
stylesheet. Keep in mind that this will only be called/rebuilt when the user changes
display settings or pretix gets updated. You will get the filename that is being
generated (usually "main.scss" or "widget.scss"). This SASS code will be loaded *after*
setting of user-defined variables like colors and fonts but *before* pretix' SASS
code.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

sass_postamble = EventPluginSignal()
"""
Arguments: ``filename``

This signal allows you to put SASS code at the end of the event-specific
stylesheet. Keep in mind that this will only be called/rebuilt when the user changes
display settings or pretix gets updated. You will get the filename that is being
generated (usually "main.scss" or "widget.scss"). This SASS code will be loaded *after*
all of pretix' SASS code.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

footer_link = EventPluginSignal()
"""
Arguments: ``request``

The signal ``pretix.presale.signals.footer_link`` allows you to add links to the footer of an event page. You
are expected to return a dictionary containing the keys ``label`` and ``url``.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

global_footer_link = Signal()
"""
Arguments: ``request``

The signal ``pretix.presale.signals.global_footer_link`` allows you to add links to the footer of any page. You
are expected to return a dictionary containing the keys ``label`` and ``url``.
"""

checkout_confirm_messages = EventPluginSignal()
"""
This signal is sent out to retrieve short messages that need to be acknowledged by the user before the
order can be completed. This is typically used for something like "accept the terms and conditions".
Receivers are expected to return a dictionary where the keys are globally unique identifiers for the
message and the values can be arbitrary HTML.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

checkout_flow_steps = EventPluginSignal()
"""
This signal is sent out to retrieve pages for the checkout flow. Receivers are expected to return
a subclass of ``pretix.presale.checkoutflow.BaseCheckoutFlowStep``.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

voucher_redeem_info = EventPluginSignal()
"""
Arguments: ``voucher``

This signal is sent out to display additional information on the "redeem a voucher" page

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

order_meta_from_request = EventPluginSignal()
"""
Arguments: ``request``

This signal is sent before an order is created through the pretixpresale frontend. It allows you
to return a dictionary that will be merged in the meta_info attribute of the order.
You will receive the request triggering the order creation as the ``request`` keyword argument.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

checkout_confirm_page_content = EventPluginSignal()
"""
Arguments: ``request``

This signals allows you to add HTML content to the confirmation page that is presented at the
end of the checkout process, just before the order is being created.

As with all plugin signals, the ``sender`` keyword argument will contain the event. A ``request``
argument will contain the request object.
"""

fee_calculation_for_cart = EventPluginSignal()
"""
Arguments: ``request``, ``invoice_address``, ``total``, ``positions``, ``payment_requetss``

This signals allows you to add fees to a cart. You are expected to return a list of ``OrderFee``
objects that are not yet saved to the database (because there is no order yet).

As with all plugin signals, the ``sender`` keyword argument will contain the event. A ``request``
argument will contain the request object and ``invoice_address`` the invoice address (useful for
tax calculation). The ``total`` keyword argument will contain the total cart sum without any fees.
You should not rely on this ``total`` value for fee calculations as other fees might interfere.
The ``positions`` argument will contain a list or queryset of ``CartPosition`` objects.
"""

contact_form_fields = EventPluginSignal()
"""
This signals allows you to add form fields to the contact form that is presented during checkout
and by default only asks for the email address. You are supposed to return a dictionary of
form fields with globally unique keys. The validated form results will be saved into the
``contact_form_data`` entry of the order's meta_info dictionary.

As with all plugin signals, the ``sender`` keyword argument will contain the event. A ``request``
argument will contain the request object.
"""

contact_form_fields_overrides = EventPluginSignal()
"""
Arguments: ``request``, ``order``

This signal allows you to override fields of the contact form that is presented during checkout
and by default only asks for the email address. It is also being used for the invoice address
form. You are supposed to return a dictionary of dictionaries with globally unique keys. The
value-dictionary should contain one or more of the following keys: ``initial``, ``disabled``,
``validators``. The key of the dictionary should be the name of the form field.

As with all plugin signals, the ``sender`` keyword argument will contain the event. A ``request``
argument will contain the request object. The ``order`` argument is ``None`` during the checkout
process and contains an order if the customer is trying to change an existing order.
"""

question_form_fields = EventPluginSignal()
"""
Arguments: ``position``

This signals allows you to add form fields to the questions form that is presented during checkout
and by default asks for the questions configured in the backend. You are supposed to return a dictionary
of form fields with globally unique keys. The validated form results will be saved into the
``question_form_data`` entry of the position's meta_info dictionary.

The ``position`` keyword argument will contain either a ``CartPosition`` object or an ``OrderPosition``
object, depending on whether the form is called as part of the order checkout or for changing an order
later.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

question_form_fields_overrides = EventPluginSignal()
"""
Arguments: ``position``, ``request``

This signal allows you to override fields of the questions form that is presented during checkout
and by default only asks for the questions configured in the backend. You are supposed to return a
dictionary of dictionaries with globally unique keys. The value-dictionary should contain one or
more of the following keys: ``initial``, ``disabled``, ``validators``. The key of the dictionary
should be the form field name for system fields (e.g. ``company``), or the question's ``identifier``
for user-defined questions.

The ``position`` keyword argument will contain a ``CartPosition`` or ``OrderPosition`` object.

As with all plugin signals, the ``sender`` keyword argument will contain the event. A ``request``
argument will contain the request object.
"""

order_info = EventPluginSignal()
"""
Arguments: ``order``, ``request``

This signal is sent out to display additional information on the order detail page

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

position_info = EventPluginSignal()
"""
Arguments: ``order``, ``position``, ``request``

This signal is sent out to display additional information on the position detail page

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

order_info_top = EventPluginSignal()
"""
Arguments: ``order``, ``request``

This signal is sent out to display additional information on top of the order detail page

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

position_info_top = EventPluginSignal()
"""
Arguments: ``order``, ``position``, ``request``

This signal is sent out to display additional information on top of the position detail page

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

process_request = EventPluginSignal()
"""
Arguments: ``request``

This signal is sent out whenever a request is made to a event presale page. Most of the
time, this will be called from the middleware layer (except on plugin-provided pages
this will be called by the @event_view decorator). Similarly to Django's process_request
middleware method, if you return a Response, that response will be used and the request
won't be processed any further down the stack.

WARNING: Be very careful about using this signal as listening to it makes it really
easy to cause serious performance problems.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

process_response = EventPluginSignal()
"""
Arguments: ``request``, ``response``

This signal is sent out whenever a response is sent from a event presale page. Most of
the time, this will be called from the middleware layer (except on plugin-provided pages
this will be called by the @event_view decorator). Similarly to Django's process_response
middleware method you must return a response object, that will be passed further up the
stack to other handlers of the signal. If you do not want to alter the response, just
return the ``response`` parameter.

WARNING: Be very careful about using this signal as listening to it makes it really
easy to cause serious performance problems.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

front_page_top = EventPluginSignal()
"""
Arguments: ``request``, ``subevent``

This signal is sent out to display additional information on the frontpage above the list
of products and but below a custom frontpage text.

As with all plugin signals, the ``sender`` keyword argument will contain the event. The
receivers are expected to return HTML.
"""

render_seating_plan = EventPluginSignal()
"""
Arguments: ``request``, ``subevent``, ``voucher``

This signal is sent out to render a seating plan, if one is configured for the specific event.
You will be passed the ``request`` as a keyword argument. If applicable, a ``subevent`` or
``voucher`` argument might be given.

As with all plugin signals, the ``sender`` keyword argument will contain the event. The
receivers are expected to return HTML.
"""

front_page_bottom = EventPluginSignal()
"""
Arguments: ``request``, ``subevent``

This signal is sent out to display additional information on the frontpage below the list
of products.

As with all plugin signals, the ``sender`` keyword argument will contain the event. The
receivers are expected to return HTML.
"""

front_page_bottom_widget = EventPluginSignal()
"""
Arguments: ``request``, ``subevent``

This signal is sent out to display additional information on the frontpage below the list
of products if the front page is shown in the widget.

As with all plugin signals, the ``sender`` keyword argument will contain the event. The
receivers are expected to return HTML.
"""

checkout_all_optional = EventPluginSignal()
"""
Arguments: 'request'

If any receiver of this signal returns ``True``, all input fields during checkout (contact data,
invoice address, confirmations) will be optional, except for questions. Use with care!

As with all plugin signals, the ``sender`` keyword argument will contain the event. A ``request``
argument will contain the request object.
"""

item_description = EventPluginSignal()
"""
Arguments: ``item``, ``variation``

This signal is sent out when the description of an item or variation is rendered and allows you to append
additional text to the description. You are passed the ``item`` and ``variation`` and expected to return
HTML.
"""

register_cookie_providers = EventPluginSignal()
"""
Arguments: ``request``

This signal is sent out to get all cookie providers that could set a cookie on this page, regardless of
consent state. Receivers should return a list of ``pretix.presale.cookies.CookieProvider`` objects.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""
