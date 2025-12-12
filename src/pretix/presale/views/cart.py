#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
# This file contains Apache-licensed contributions copyrighted by: Ben Hagan, FlaviaBastos, Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import json
import mimetypes
import os
import urllib
from decimal import Decimal
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import translation
from django.utils.crypto import get_random_string
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.timezone import now
from django.utils.translation import gettext as _, pgettext
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import TemplateView, View
from django_scopes import scopes_disabled

from pretix.base.models import (
    CartPosition, GiftCard, InvoiceAddress, QuestionAnswer, SubEvent, Voucher,
)
from pretix.base.services.cart import (
    CartError, add_items_to_cart, apply_voucher, clear_cart, error_messages,
    extend_cart_reservation, remove_cart_position,
)
from pretix.base.timemachine import time_machine_now
from pretix.base.views.tasks import AsyncAction
from pretix.helpers.http import redirect_to_url
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.views import (
    CartMixin, EventViewMixin, allow_cors_if_namespaced,
    allow_frame_if_namespaced, get_cart, iframe_entry_view_wrapper,
)
from pretix.presale.views.event import (
    get_grouped_items, item_group_by_category,
)
from pretix.presale.views.robots import NoSearchIndexViewMixin

try:
    widget_data_cache = caches['redis']
except:
    widget_data_cache = caches['default']


class CartActionMixin:

    def get_next_url(self):
        if "next" in self.request.GET and url_has_allowed_host_and_scheme(self.request.GET.get("next"), allowed_hosts=None):
            u = self.request.GET.get('next')
        else:
            kwargs = {}
            if 'cart_namespace' in self.kwargs:
                kwargs['cart_namespace'] = self.kwargs['cart_namespace']
            u = eventreverse(self.request.event, 'presale:event.index', kwargs=kwargs)

        query = {'require_cookie': 'true'}

        if 'locale' in self.request.GET:
            query['locale'] = self.request.GET['locale']
        disclose_cart_id = (
            'iframe' in self.request.GET or (
                settings.SESSION_COOKIE_NAME not in self.request.COOKIES and
                '__Host-' + settings.SESSION_COOKIE_NAME not in self.request.COOKIES
            )
        ) and self.kwargs.get('cart_namespace')
        if disclose_cart_id:
            cart_id = get_or_create_cart_id(self.request)
            query['cart_id'] = cart_id

        if '?' in u:
            u += '&' + urllib.parse.urlencode(query)
        else:
            u += '?' + urllib.parse.urlencode(query)
        return u

    def get_success_url(self, value=None):
        return self.get_next_url()

    def get_error_url(self):
        if "next_error" in self.request.GET and url_has_allowed_host_and_scheme(self.request.GET.get("next_error"), allowed_hosts=None):
            u = self.request.GET.get('next_error')
            if '?' in u:
                u += '&require_cookie=true'
            else:
                u += '?require_cookie=true'
            disclose_cart_id = (
                'iframe' in self.request.GET or (
                    settings.SESSION_COOKIE_NAME not in self.request.COOKIES and
                    '__Host-' + settings.SESSION_COOKIE_NAME not in self.request.COOKIES
                )
            ) and self.kwargs.get('cart_namespace')
            if disclose_cart_id:
                cart_id = get_or_create_cart_id(self.request)
                u += '&cart_id={}'.format(cart_id)
            return u
        return self.get_next_url()

    @cached_property
    def cart_session(self):
        return cart_session(self.request)

    @cached_property
    def invoice_address(self):
        iapk = self.cart_session.get('invoice_address')
        if not iapk:
            return InvoiceAddress()

        try:
            with scopes_disabled():
                return InvoiceAddress.objects.get(pk=iapk, order__isnull=True)
        except InvoiceAddress.DoesNotExist:
            return InvoiceAddress()


def _item_from_post_value(request, key, value, voucher=None, voucher_ignore_if_redeemed=False):
    if value.strip() == '' or '_' not in key:
        return

    subevent = None
    prefix = ''
    if key.startswith('subevent_'):
        try:
            parts = key.split('_', 2)
            subevent = int(parts[1])
            key = parts[2]
            prefix = f'subevent_{subevent}_'
        except ValueError:
            pass
    elif 'subevent' in request.POST:
        try:
            subevent = int(request.POST.get('subevent'))
        except ValueError:
            pass

    if not key.startswith('item_') and not key.startswith('variation_') and not key.startswith('seat_'):
        return

    parts = key.split("_")
    price = request.POST.get(prefix + 'price_' + "_".join(parts[1:]), "")

    if key.startswith('seat_'):
        try:
            return {
                'item': int(parts[1]),
                'variation': int(parts[2]) if len(parts) > 2 else None,
                'count': 1,
                'seat': value,
                'price': price,
                'voucher': voucher,
                'voucher_ignore_if_redeemed': voucher_ignore_if_redeemed,
                'subevent': subevent
            }
        except ValueError:
            raise CartError(_('Please enter numbers only.'))

    try:
        amount = int(value)
    except ValueError:
        raise CartError(_('Please enter numbers only.'))
    if amount < 0:
        raise CartError(_('Please enter positive numbers only.'))
    elif amount == 0:
        return

    if key.startswith('item_'):
        try:
            return {
                'item': int(parts[1]),
                'variation': None,
                'count': amount,
                'price': price,
                'voucher': voucher,
                'voucher_ignore_if_redeemed': voucher_ignore_if_redeemed,
                'subevent': subevent
            }
        except ValueError:
            raise CartError(_('Please enter numbers only.'))
    elif key.startswith('variation_'):
        try:
            return {
                'item': int(parts[1]),
                'variation': int(parts[2]),
                'count': amount,
                'price': price,
                'voucher': voucher,
                'voucher_ignore_if_redeemed': voucher_ignore_if_redeemed,
                'subevent': subevent
            }
        except ValueError:
            raise CartError(_('Please enter numbers only.'))


def _items_from_post_data(request, warn_if_empty=True):
    """
    Parses the POST data and returns a list of dictionaries
    """

    # Compatibility patch that makes the frontend code a lot easier
    req_items = list(request.POST.lists())
    if '_voucher_item' in request.POST and '_voucher_code' in request.POST:
        req_items.append((
            '%s' % request.POST['_voucher_item'], ('1',)
        ))
        pass

    items = []
    if 'raw' in request.POST:
        items += json.loads(request.POST.get("raw"))
    for key, values in req_items:
        for value in values:
            try:
                item = _item_from_post_value(request, key, value, request.POST.get('_voucher_code'),
                                             voucher_ignore_if_redeemed=request.POST.get('_voucher_ignore_if_redeemed') == 'on')
            except CartError as e:
                messages.error(request, str(e))
                return
            if item:
                items.append(item)

    if len(items) == 0 and warn_if_empty:
        messages.warning(request, _('You did not select any products.'))
        return []
    return items


@scopes_disabled()
def generate_cart_id(request=None, prefix=''):
    """
    Generates a random new cart ID that is not currently in use, with an optional pretix.
    """
    while True:
        new_id = prefix + get_random_string(length=48 - len(prefix))
        if request:
            if not request.session.session_key:
                request.session.create()
            new_id += "@" + request.session.session_key
        if not CartPosition.objects.filter(cart_id=new_id).exists():
            return new_id


def create_empty_cart_id(request, replace_current=True):
    """
    Forcefully creates a new empty cart for the current session. Behaves like get_or_create_cart_id,
    except that it ignores the current state of the session. If replace_current is active, the
    current cart session for this event is deleted as well.

    This is currently only invoked after an order has been created to make sure that all forms during
    checkout will show empty again if the same browser starts buying tickets again.
    """
    session_keyname = 'current_cart_event_{}'.format(request.event.pk)
    prefix = ''
    if request.resolver_match and request.resolver_match.kwargs.get('cart_namespace'):
        session_keyname += '_' + request.resolver_match.kwargs.get('cart_namespace')
        prefix = request.resolver_match.kwargs.get('cart_namespace')

    if 'carts' not in request.session:
        request.session['carts'] = {}

    new_id = generate_cart_id(request, prefix=prefix)
    request.session['carts'][new_id] = {}

    if replace_current:
        current_id = request.session.get(session_keyname)
        if current_id and current_id in request.session.get('carts', {}):
            del request.session['carts'][current_id]
            del request.session[session_keyname]
        request.session[session_keyname] = new_id
    return new_id


def get_or_create_cart_id(request, create=True):
    """
    This method returns the cart ID in use for this request or creates a new cart ID if required.

    Before pretix 1.8.0, the user's session cookie was used as the cart ID in the database.
    With the cart session data isolation introduced in 1.8.0 (see cart_session()) this changed
    drastically. Now, a different random cart ID is used for every event and stored to the
    user's session with the 'current_cart_event_42' key (with 42 being the event ID).

    This became even more relevant and complex with the introduction of the pretix widget in 1.9.0.
    Since the widget operates from a different origin, it requires us to lower some security walls
    in order to function correctly:

    * The checkout and order views can no longer send X-Frame-Options: DENY headers as we include
      those pages in an iframe. This makes our users vulnerable to clickjacking. Possible scenario: A
      third-party website could trick you into submitting an order that you currently have in your cart.

    * The cart add view needs to drop CSRF protection and set Access-Control-Allow-Origin: *. This makes
      our users vulnerable to CSRF attacks adding unwanted products to their carts. Cross-Origin is not
      that much of an issue since we can't set Access-Control-Allow-Credentials for origin * either way,
      but on the other hand this also prevents us to change the current cart for legitimate reasons.

    We can mitigate all of these issues at the same time with the very simple strategy on only lowering
    these walls at unguessable URLs. This makes it impossible for an attacker to create an exploit with
    real-world impact.

    Therefore, we introduce cart namespacing in pretix 1.9.0. In addition to your default session that you
    have at /orga/event/ as usual, you will have a different cart session with a different cart ID at
    /orga/event/w/mysecretnonce123/. Such a namespace parameter can be passed to all views relevant to the
    widget (e.g. /orga/event/w/mysecretnonce123/cart/add) that are not already unguessable
    (like /orga/event/orders/ABCDE/secret123465456/).

    The actual cart IDs for those namespaced carts will then be stored at
    request.session['current_cart_event_42_mysecretnonce123'].

    However, we still need to work around the issue that we can't use Access-Control-Allow-Credentials
    but want to invoke /cart/add via a cross-origin request. This leads to /cart/add creating a new
    cart session every time it is invoked cross-origin by default. We solve this by returning the newly
    created cart ID from /cart/add in the response and allow passing it as the take_cart_id query parameter
    to the view in the iframe or to subsequent /cart/add requests.

    As an additional precaution, take_cart_id will only be honoured on POST requests or if there is an
    actual cart with this ID. This reduces the likelihood of strange behaviour if someone accidentally
    shares a link that includes this parameter.

    This method migrates legacy sessions created before the upgrade to 1.8.0 on a best-effort basis,
    meaning that the migration does not respect plugin-specific data and works best if the user only
    used the session for one event at the time of migration.

    If ``create`` is ``False`` and no session currently exists, ``None`` will be returned.
    """
    session_keyname = 'current_cart_event_{}'.format(request.event.pk)
    prefix = ''
    if request.resolver_match and request.resolver_match.kwargs.get('cart_namespace'):
        session_keyname += '_' + request.resolver_match.kwargs.get('cart_namespace')
        prefix = request.resolver_match.kwargs.get('cart_namespace')

    current_id = orig_current_id = request.session.get(session_keyname)
    if prefix and 'take_cart_id' in request.GET:
        pos = CartPosition.objects.filter(event=request.event, cart_id=request.GET.get('take_cart_id'))
        if request.method == "POST" or pos.exists() or 'ajax' in request.GET:
            current_id = request.GET.get('take_cart_id')

    if current_id and current_id in request.session.get('carts', {}):
        if current_id != orig_current_id:
            request.session[session_keyname] = current_id

        cart_invalidated = (
            request.session['carts'][current_id].get('customer_cart_tied_to_login', False) and
            request.session['carts'][current_id].get('customer') and
            (not request.customer or request.session['carts'][current_id].get('customer') != request.customer.pk)
        )

        if cart_invalidated:
            # This cart was created with a login but the person is now logged out.
            # Destroy the cart for privacy protection.
            if 'carts' in request.session:
                request.session['carts'][current_id] = {}
        else:
            return current_id

    cart_data = {}
    if prefix and 'take_cart_id' in request.GET and current_id:
        new_id = current_id
        cached_widget_data = widget_data_cache.get('widget_data_{}'.format(current_id))
        if cached_widget_data:
            cart_data['widget_data'] = cached_widget_data
    else:
        if not create:
            return None
        new_id = generate_cart_id(request, prefix=prefix)

    if 'widget_data' not in cart_data and 'widget_data' in request.GET:
        try:
            cart_data['widget_data'] = json.loads(request.GET.get('widget_data'))
        except ValueError:
            pass

    if 'carts' not in request.session:
        request.session['carts'] = {}

    if new_id not in request.session['carts']:
        request.session['carts'][new_id] = cart_data

    request.session[session_keyname] = new_id
    return new_id


def cart_session(request):
    """
    Before pretix 1.8.0, all checkout-related information (like the entered email address) was stored
    in the user's regular session dictionary. This led to data interference and leaks for example if a
    user simultaneously buys tickets for two events.

    Starting with 1.8.0, this information is stored in separate dictionaries in the user's session within
    the new request.session['carts'] dictionary. This method provides convenient access to the currently
    active cart session sub-dictionary for read and write access.
    """
    request.session.modified = True
    cart_id = get_or_create_cart_id(request)
    return request.session['carts'][cart_id]


@method_decorator(allow_frame_if_namespaced, 'dispatch')
class CartApplyVoucher(EventViewMixin, CartActionMixin, AsyncAction, View):
    task = apply_voucher
    known_errortypes = ['CartError', 'CartPositionError']

    def get_success_message(self, value):
        return _('We applied the voucher to as many products in your cart as we could.')

    def post(self, request, *args, **kwargs):
        from pretix.base.payment import GiftCardPayment, GiftCardPaymentForm

        if 'voucher' in request.POST:
            code = request.POST.get('voucher').strip()

            if not self.request.event.vouchers.filter(code__iexact=code):
                try:
                    gc = self.request.event.organizer.accepted_gift_cards.get(secret=code)
                    gcp = GiftCardPayment(self.request.event)
                    if not gcp.is_enabled or not gcp.is_allowed(self.request, Decimal("1.00")):
                        raise ValidationError(error_messages['voucher_invalid'])
                    else:
                        cs = cart_session(request)
                        used_cards = [
                            p.get('info_data', {}).get('gift_card')
                            for p in cs.get('payments', [])
                            if p.get('info_data', {}).get('gift_card')
                        ]
                        form = GiftCardPaymentForm(
                            event=request.event,
                            used_cards=used_cards,
                            positions=get_cart(request),
                            testmode=request.event.testmode,
                            data={'code': code},
                        )
                        form.fields = gcp.payment_form_fields
                        if not form.is_valid():
                            # raise first validation-error in form
                            raise next(iter(form.errors.as_data().values()))[0]
                        gcp._add_giftcard_to_cart(cs, gc)
                        messages.success(
                            request,
                            _("The gift card has been saved to your cart. Please continue your checkout.")
                        )
                        if "ajax" in self.request.POST or "ajax" in self.request.GET:
                            return JsonResponse({
                                'ready': True,
                                'success': True,
                                'redirect': self.get_success_url(),
                                'message': str(
                                    _("The gift card has been saved to your cart. Please continue your checkout.")
                                )
                            })
                        return redirect_to_url(self.get_success_url())
                except GiftCard.DoesNotExist:
                    pass
                except ValidationError as e:
                    messages.error(self.request, str(e.message))
                    if "ajax" in self.request.POST or "ajax" in self.request.GET:
                        return JsonResponse({
                            'ready': True,
                            'success': False,
                            'redirect': self.get_success_url(),
                            'message': str(e.message)
                        })
                    return redirect_to_url(self.get_error_url())

            return self.do(self.request.event.id, code, get_or_create_cart_id(self.request),
                           translation.get_language(), request.sales_channel.identifier,
                           time_machine_now(default=None))
        else:
            if 'ajax' in self.request.GET or 'ajax' in self.request.POST:
                return JsonResponse({
                    'redirect': self.get_error_url()
                })
            else:
                return redirect_to_url(self.get_error_url())


@method_decorator(allow_frame_if_namespaced, 'dispatch')
class CartRemove(EventViewMixin, CartActionMixin, AsyncAction, View):
    task = remove_cart_position
    known_errortypes = ['CartError', 'CartPositionError']

    def get_success_message(self, value):
        if CartPosition.objects.filter(cart_id=get_or_create_cart_id(self.request)).exists():
            return _('Your cart has been updated.')
        else:
            create_empty_cart_id(self.request)
            return _('Your cart is now empty.')

    def post(self, request, *args, **kwargs):
        if 'id' in request.POST:
            try:
                return self.do(self.request.event.id, int(request.POST.get('id')), get_or_create_cart_id(self.request),
                               translation.get_language(), request.sales_channel.identifier,
                               time_machine_now(default=None))
            except ValueError:
                return redirect_to_url(self.get_error_url())
        else:
            if 'ajax' in self.request.GET or 'ajax' in self.request.POST:
                return JsonResponse({
                    'redirect': self.get_error_url()
                })
            else:
                return redirect_to_url(self.get_error_url())


@method_decorator(allow_frame_if_namespaced, 'dispatch')
class CartClear(EventViewMixin, CartActionMixin, AsyncAction, View):
    task = clear_cart
    known_errortypes = ['CartError', 'CartPositionError']

    def get_success_message(self, value):
        create_empty_cart_id(self.request)
        return _('Your cart is now empty.')

    def post(self, request, *args, **kwargs):
        return self.do(self.request.event.id, get_or_create_cart_id(self.request), translation.get_language(),
                       request.sales_channel.identifier, time_machine_now(default=None))


@method_decorator(allow_frame_if_namespaced, 'dispatch')
class CartExtendReservation(EventViewMixin, CartActionMixin, AsyncAction, View):
    task = extend_cart_reservation
    known_errortypes = ['CartError', 'CartPositionError']

    def _ajax_response_data(self, value):
        if isinstance(value, dict):
            return value
        else:
            return {}

    def get_success_message(self, value):
        if value['success'] > 0:
            if value.get('price_changed'):
                return _('Your cart timeout was extended. Please note that some of the prices in your cart '
                         'changed.')
            else:
                return _('Your cart timeout was extended.')

    def post(self, request, *args, **kwargs):
        return self.do(self.request.event.id, get_or_create_cart_id(self.request), translation.get_language(),
                       request.sales_channel.identifier, time_machine_now(default=None))


@method_decorator(allow_cors_if_namespaced, 'dispatch')
@method_decorator(allow_frame_if_namespaced, 'dispatch')
@method_decorator(iframe_entry_view_wrapper, 'dispatch')
class CartAdd(EventViewMixin, CartActionMixin, AsyncAction, View):
    task = add_items_to_cart
    known_errortypes = ['CartError', 'CartPositionError']

    def get_success_message(self, value):
        return _('The products have been successfully added to your cart.')

    def _ajax_response_data(self, value):
        cart_id = get_or_create_cart_id(self.request)
        return {
            'cart_id': cart_id,
            'has_cart': CartPosition.objects.filter(cart_id=cart_id, event=self.request.event).exists()
        }

    def get_check_url(self, task_id, ajax):
        u = super().get_check_url(task_id, ajax)
        if "next" in self.request.GET:
            u += "&next=" + quote(self.request.GET.get('next'))
        if "locale" in self.request.GET and "locale=" not in u:
            u += "&locale=" + quote(self.request.GET.get('locale'))
        if "next_error" in self.request.GET:
            u += "&next_error=" + quote(self.request.GET.get('next_error'))
        if ajax:
            cart_id = get_or_create_cart_id(self.request)
            u += '&take_cart_id=' + cart_id
        return u

    def post(self, request, *args, **kwargs):
        if not request.event.all_sales_channels and request.sales_channel.identifier not in (s.identifier for s in request.event.limit_sales_channels.all()):
            raise Http404(_('Tickets for this event cannot be purchased on this sales channel.'))

        cart_id = get_or_create_cart_id(self.request)
        if "widget_data" in request.POST:
            try:
                widget_data = json.loads(request.POST.get("widget_data", "{}"))
                if not isinstance(widget_data, dict):
                    widget_data = {}
            except ValueError:
                widget_data = {}
            else:
                widget_data_cache.set('widget_data_{}'.format(cart_id), widget_data, 600)
                cs = cart_session(request)
                cs['widget_data'] = widget_data
        else:
            cs = cart_session(request)
            widget_data = cs.get('widget_data', {})

        items = _items_from_post_data(self.request)
        if items:
            return self.do(self.request.event.id, items, cart_id, translation.get_language(),
                           self.invoice_address.pk, widget_data, self.request.sales_channel.identifier,
                           time_machine_now(default=None))
        else:
            if 'ajax' in self.request.GET or 'ajax' in self.request.POST:
                return JsonResponse({
                    'redirect': self.get_error_url(),
                    'success': False,
                    'message': str(error_messages['empty'])
                })
            else:
                return redirect_to_url(self.get_error_url())


@method_decorator(allow_frame_if_namespaced, 'dispatch')
@method_decorator(iframe_entry_view_wrapper, 'dispatch')
class RedeemView(NoSearchIndexViewMixin, EventViewMixin, CartMixin, TemplateView):
    template_name = "pretixpresale/event/voucher.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['voucher'] = self.voucher
        context['max_times'] = self.voucher.max_usages - self.voucher.redeemed

        # Fetch all items
        items, display_add_to_cart = get_grouped_items(
            self.request.event,
            subevent=self.subevent,
            voucher=self.voucher,
            channel=self.request.sales_channel,
            memberships=(
                self.request.customer.usable_memberships(
                    for_event=self.subevent or self.request.event,
                    testmode=self.request.event.testmode
                ) if getattr(self.request, 'customer', None) else None
            ),
        )

        # Calculate how many options the user still has. If there is only one option, we can
        # check the box right away ;)
        context['options'] = sum([(len(item.available_variations) if item.has_variations else 1)
                                  for item in items])

        context['allfree'] = all(
            item.display_price.gross == Decimal('0.00') and not item.mandatory_priced_addons
            for item in items if not item.has_variations
        ) and all(
            all(
                var.display_price.gross == Decimal('0.00')
                for var in item.available_variations
            ) and not item.mandatory_priced_addons
            for item in items if item.has_variations
        )

        context['cart'] = self.get_cart()
        context['show_cart'] = context['cart']['positions']

        # Regroup those by category
        context['items_by_category'] = item_group_by_category(items)

        context['subevent'] = self.subevent
        context['seating_available'] = self.request.event.settings.seating_choice and self.voucher.seating_available(self.subevent)

        context['new_tab'] = (
            'require_cookie' in self.request.GET and
            settings.SESSION_COOKIE_NAME not in self.request.COOKIES and
            '__Host-' + settings.SESSION_COOKIE_NAME not in self.request.COOKIES
            # Cookies are not supported! Lets just make the form open in a new tab
        )

        if self.request.event.settings.redirect_to_checkout_directly:
            context['cart_redirect'] = eventreverse(self.request.event, 'presale:event.checkout.start',
                                                    kwargs={'cart_namespace': kwargs.get('cart_namespace') or ''})
        else:
            if 'next' in self.request.GET and url_has_allowed_host_and_scheme(self.request.GET.get("next"), allowed_hosts=None):
                context['cart_redirect'] = self.request.GET.get('next')
            else:
                context['cart_redirect'] = eventreverse(self.request.event, 'presale:event.index',
                                                        kwargs={'cart_namespace': kwargs.get('cart_namespace') or ''})
        if context['cart_redirect'].startswith('https:'):
            context['cart_redirect'] = '/' + context['cart_redirect'].split('/', 3)[3]
        return context

    def dispatch(self, request, *args, **kwargs):
        from pretix.base.payment import GiftCardPayment, GiftCardPaymentForm

        err = None
        v = request.GET.get('voucher')

        if v:
            v = v.strip()
            try:
                self.voucher = Voucher.objects.get(code__iexact=v, event=request.event)
                if self.voucher.redeemed >= self.voucher.max_usages:
                    err = error_messages['voucher_redeemed']
                if self.voucher.valid_until is not None and self.voucher.valid_until < now():
                    err = error_messages['voucher_expired']
                if self.voucher.item is not None and self.voucher.item.is_available() is False:
                    err = error_messages['voucher_item_not_available']

                redeemed_in_carts = CartPosition.objects.filter(
                    Q(voucher=self.voucher) & Q(event=request.event) &
                    (Q(expires__gte=now()) | Q(cart_id=get_or_create_cart_id(request)))
                )
                v_avail = self.voucher.max_usages - self.voucher.redeemed - redeemed_in_carts.count()
                if v_avail < 1 and not err:
                    err = error_messages['voucher_redeemed_cart'] % self.request.event.settings.reservation_time
            except Voucher.DoesNotExist:
                try:
                    gc = request.event.organizer.accepted_gift_cards.get(secret=v)
                    gcp = GiftCardPayment(request.event)
                    if not gcp.is_enabled or not gcp.is_allowed(request, Decimal("1.00")):
                        err = error_messages['voucher_invalid']
                    else:
                        cs = cart_session(request)
                        used_cards = [
                            p.get('info_data', {}).get('gift_card')
                            for p in cs.get('payments', [])
                            if p.get('info_data', {}).get('gift_card')
                        ]
                        form = GiftCardPaymentForm(
                            event=request.event,
                            used_cards=used_cards,
                            positions=get_cart(request),
                            testmode=request.event.testmode,
                            data={'code': v},
                        )
                        form.fields = gcp.payment_form_fields
                        if not form.is_valid():
                            # raise first validation-error in form
                            raise next(iter(form.errors.as_data().values()))[0]
                        gcp._add_giftcard_to_cart(cs, gc)
                        messages.success(
                            request,
                            _("The gift card has been saved to your cart. Please now select the products "
                              "you want to purchase.")
                        )
                        return redirect_to_url(self.get_next_url())
                except GiftCard.DoesNotExist:
                    err = error_messages['voucher_invalid']
                except ValidationError as e:
                    err = str(e.message)
        else:
            context = {}
            context['cart'] = self.get_cart()
            context['show_cart'] = context['cart']['positions']
            return render(request, 'pretixpresale/event/voucher_form.html', context)

        if request.event.presale_has_ended or (
                request.event.presale_end and time_machine_now() > request.event.presale_end):
            err = error_messages['ended']
        elif not request.event.presale_is_running or (
                request.event.presale_start and time_machine_now() < request.event.presale_start):
            err = error_messages['not_started']

        self.subevent = None
        if request.event.has_subevents:
            if request.GET.get('subevent'):
                try:
                    subevent_pk = int(request.GET.get('subevent'))
                    self.subevent = request.event.subevents.get(pk=subevent_pk, active=True)
                except (ValueError, SubEvent.DoesNotExist):
                    raise Http404(pgettext('subevent', 'We were unable to find the specified date.'))

            if hasattr(self, 'voucher') and self.voucher.subevent:
                self.subevent = self.voucher.subevent

            if not err and not self.subevent:
                return redirect_to_url(
                    eventreverse(
                        self.request.event, 'presale:event.index',
                        kwargs={'cart_namespace': kwargs.get('cart_namespace') or ''}
                    ) + '?voucher=' + quote(self.voucher.code)
                )
        else:
            pass

        if err:
            messages.error(request, str(err))
            return redirect_to_url(self.get_next_url() + "?voucher_invalid")

        return super().dispatch(request, *args, **kwargs)

    def get_next_url(self):
        if "next" in self.request.GET and url_has_allowed_host_and_scheme(self.request.GET.get("next"), allowed_hosts=None):
            return self.request.GET.get("next")
        return self.get_index_url()

    def get(self, request, *args, **kwargs):
        if 'iframe' in request.GET and 'require_cookie' not in request.GET:
            return redirect_to_url(request.get_full_path() + '&require_cookie=1')

        if len(self.request.GET.get('widget_data', '{}')) > 3:
            # We've been passed data from a widget, we need to create a cart session to store it.
            get_or_create_cart_id(request)
        return super().get(request, *args, **kwargs)


@method_decorator(xframe_options_exempt, 'dispatch')
class AnswerDownload(EventViewMixin, View):
    def get(self, request, *args, **kwargs):
        answid = kwargs.get('answer')
        answer = get_object_or_404(
            QuestionAnswer,
            cartposition__cart_id=get_or_create_cart_id(self.request),
            id=answid
        )
        if not answer.file:
            return Http404()

        ftype, _ = mimetypes.guess_type(answer.file.name)
        resp = FileResponse(answer.file, content_type=ftype or 'application/binary')
        resp['Content-Disposition'] = 'attachment; filename="{}-cart-{}"'.format(
            self.request.event.slug.upper(),
            os.path.basename(answer.file.name).split('.', 1)[1]
        ).encode("ascii", "ignore")
        return resp
