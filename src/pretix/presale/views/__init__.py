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
# This file contains Apache-licensed contributions copyrighted by: Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.
import copy
import warnings
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from functools import wraps
from itertools import groupby

from django.conf import settings
from django.contrib import messages
from django.db.models import Exists, OuterRef, Prefetch, Sum
from django.utils import translation
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_scopes import scopes_disabled

from pretix.base.i18n import get_language_without_region, set_region
from pretix.base.middleware import get_supported_language
from pretix.base.models import (
    CartPosition, Customer, InvoiceAddress, ItemAddOn, OrderFee, Question,
    QuestionAnswer, QuestionOption, TaxRule,
)
from pretix.base.services.cart import get_fees
from pretix.base.services.pricing import apply_rounding
from pretix.base.templatetags.money import money_filter
from pretix.helpers.cookies import set_cookie_without_samesite
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.signals import question_form_fields


def cached_invoice_address(request):
    from .cart import cart_session

    if not hasattr(request, '_checkout_flow_invoice_address'):
        if not request.session.session_key:
            # do not create a session, if we don't have a session we also don't have an invoice address ;)
            request._checkout_flow_invoice_address = InvoiceAddress()
            return request._checkout_flow_invoice_address
        cs = cart_session(request)
        iapk = cs.get('invoice_address')
        if not iapk:
            request._checkout_flow_invoice_address = InvoiceAddress()
        else:
            try:
                with scopes_disabled():
                    request._checkout_flow_invoice_address = InvoiceAddress.objects.get(
                        pk=iapk, order__isnull=True
                    )
            except InvoiceAddress.DoesNotExist:
                request._checkout_flow_invoice_address = InvoiceAddress()
    return request._checkout_flow_invoice_address


class CartMixin:
    @cached_property
    def positions(self):
        """
        A list of this users cart position
        """
        return list(get_cart(self.request))

    @cached_property
    def cart_session(self):
        from pretix.presale.views.cart import cart_session
        return cart_session(self.request)

    @cached_property
    def cart_customer(self):
        if self.cart_session.get('customer_mode', 'guest') == 'login':
            try:
                return self.request.organizer.customers.get(pk=self.cart_session.get('customer', -1))
            except Customer.DoesNotExist:
                return

    @cached_property
    def invoice_address(self):
        return cached_invoice_address(self.request)

    def get_cart(self, answers=False, queryset=None, order=None, downloads=False, payments=None):
        if queryset is not None:
            prefetch = []
            if answers:
                prefetch.append('item__questions')
                prefetch.append(Prefetch('answers', queryset=QuestionAnswer.objects.prefetch_related('options')))

            cartpos = queryset.order_by(
                'item__category__position', 'item__category_id', 'item__position', 'item__name',
                'variation__value'
            ).select_related(
                'item', 'variation', 'addon_to', 'subevent', 'subevent__event',
                'subevent__event__organizer', 'seat'
            ).prefetch_related(
                *prefetch
            )

        else:
            cartpos = self.positions

        lcp = list(cartpos)
        has_addons = defaultdict(list)
        for cp in lcp:
            if cp.addon_to_id:
                has_addons[cp.addon_to_id].append(cp)

        pos_additional_fields = defaultdict(list)
        for cp in lcp:
            cp.item.event = self.request.event  # will save some SQL queries
            responses = question_form_fields.send(sender=self.request.event, position=cp)
            data = cp.meta_info_data
            for r, response in sorted(responses, key=lambda r: str(r[0])):
                if response:
                    for key, value in response.items():
                        pos_additional_fields[cp.pk].append({
                            'answer': data.get('question_form_data', {}).get(key),
                            'question': value.label
                        })

        if order:
            fees = order.fees.all()
        elif lcp:
            try:
                fees = get_fees(
                    event=self.request.event,
                    request=self.request,
                    invoice_address=self.invoice_address,
                    payments=payments if payments is not None else self.cart_session.get('payments', []),
                    positions=cartpos,
                )
            except TaxRule.SaleNotAllowed:
                # ignore for now, will fail on order creation
                fees = []
        else:
            fees = []

        if not order:
            apply_rounding(self.request.event.settings.tax_rounding, self.invoice_address, self.request.event.currency, [*lcp, *fees])

        total = sum([c.price for c in lcp]) + sum([f.value for f in fees])
        net_total = sum(p.price - p.tax_value for p in lcp) + sum([f.net_value for f in fees])
        tax_total = sum(p.tax_value for p in lcp) + sum([f.tax_value for f in fees])

        # Group items of the same variation
        # We do this by list manipulations instead of a GROUP BY query, as
        # Django is unable to join related models in a .values() query
        def group_key(pos):  # only used for grouping, sorting is done before already
            has_attendee_data = pos.item.ask_attendee_data and (
                self.request.event.settings.attendee_names_asked
                or self.request.event.settings.attendee_emails_asked
                or self.request.event.settings.attendee_company_asked
                or self.request.event.settings.attendee_addresses_asked
                or pos_additional_fields.get(pos.pk)
            )
            grouping_allowed = (
                # Never group when we have per-ticket download buttons
                not downloads and
                # Never group if the position has add-ons
                pos.pk not in has_addons and
                # Never group if we have answers to show
                (not answers or (not has_attendee_data and not bool(pos.item.questions.all()))) and  # do not use .exists() to re-use prefetch cache
                # Never group when we have a final order and a gift card code
                (isinstance(pos, CartPosition) or not pos.item.issue_giftcard)
            )

            if not grouping_allowed:
                return (pos.pk,)
            else:
                return (
                    (pos.addon_to_id or 0),
                    pos.subevent_id,
                    pos.item_id,
                    pos.variation_id,
                    pos.net_price if self.request.event.settings.display_net_prices else pos.price,
                    (pos.voucher_id or 0),
                    (pos.seat_id or 0),
                    pos.valid_from,
                    pos.valid_until,
                    pos.used_membership_id,
                    pos.gross_price_before_rounding,
                    pos.tax_value_before_rounding,
                )

        positions = []
        for k, g in groupby(sorted(lcp, key=lambda c: c.sort_key), key=group_key):
            g = list(g)
            group = g[0]
            group.count = len(g)
            group.total = group.count * group.price
            group.net_total = group.count * group.net_price
            group.has_questions = answers and k[0] != ""
            if not hasattr(group, 'tax_rule'):
                group.tax_rule = group.item.tax_rule

            group.price_for_input = group.gross_price_before_rounding + sum(a.gross_price_before_rounding for a in has_addons[group.pk])
            group.price_for_input_net = group.net_price_before_rounding + sum(a.net_price_before_rounding for a in has_addons[group.pk])

            if answers:
                group.cache_answers(all=False)
                group.additional_answers = pos_additional_fields.get(group.pk)
            positions.append(group)

        try:
            first_expiry = min(p.expires for p in positions) if positions else now()
            max_expiry_extend = min((p.max_extend for p in positions if p.max_extend), default=None)
            total_seconds_left = max(first_expiry - now(), timedelta()).total_seconds()
            minutes_left = int(total_seconds_left // 60)
            seconds_left = int(total_seconds_left % 60)
        except AttributeError:
            first_expiry = None
            max_expiry_extend = None
            minutes_left = None
            seconds_left = None

        itemvarsums = Counter()
        for p in cartpos:
            itemvarsums[p.variation or p.item] += 1

        return {
            'positions': positions,
            'invoice_address': self.invoice_address,
            'all_with_voucher': all(p.voucher_id for p in positions),
            'raw': cartpos,
            'total': total,
            'net_total': net_total,
            'tax_total': tax_total,
            'fees': fees,
            'answers': answers,
            'minutes_left': minutes_left,
            'seconds_left': seconds_left,
            'first_expiry': first_expiry,
            'max_expiry_extend': max_expiry_extend,
            'is_ordered': bool(order),
            'itemcount': sum(c.count for c in positions if not c.addon_to),
            'show_rounding_info': (
                self.request.event.settings.tax_rounding == "sum_by_net_only_business" and
                not self.request.event.settings.display_net_prices and
                sum(c.price_includes_rounding_correction for c in positions) + sum(f.price_includes_rounding_correction for f in fees)
            ),
            'itemvarsums': itemvarsums,
            'current_selected_payments': [
                p for p in self.current_selected_payments(lcp, fees, self.invoice_address)
                if p.get('multi_use_supported')
            ]
        }

    def current_selected_payments(self, positions, fees, invoice_address, *, warn=False):
        raw_payments = copy.deepcopy(self.cart_session.get('payments', []))
        fees = [f for f in fees if f.fee_type != OrderFee.FEE_TYPE_PAYMENT]  # we re-compute these here

        apply_rounding(self.request.event.settings.tax_rounding, invoice_address, self.request.event.currency, [*positions, *fees])
        total = sum([c.price for c in positions]) + sum([f.value for f in fees])

        payments = []
        payments_assigned = Decimal("0.00")
        for p in raw_payments:
            # This algorithm of treating min/max values and fees needs to stay in sync between the following
            # places in the code base:
            # - pretix.base.services.cart.get_fees
            # - pretix.base.services.orders._get_fees
            # - pretix.presale.views.CartMixin.current_selected_payments
            if p.get('min_value') and total - payments_assigned < Decimal(p['min_value']):
                if warn:
                    messages.warning(
                        self.request,
                        _('Your selected payment method can only be used for a payment of at least {amount}.').format(
                            amount=money_filter(Decimal(p['min_value']), self.request.event.currency)
                        )
                    )
                self._remove_payment(p['id'])
                continue

            to_pay = max(total - payments_assigned, Decimal("0.00"))
            if p.get('max_value') and to_pay > Decimal(p['max_value']):
                to_pay = min(to_pay, Decimal(p['max_value']))

            pprov = self.request.event.get_payment_providers(cached=True).get(p['provider'])
            if not pprov:
                self._remove_payment(p['id'])
                continue

            payment_fee = pprov.calculate_fee(to_pay)
            if payment_fee:
                if self.request.event.settings.tax_rule_payment == "default":
                    payment_fee_tax_rule = self.request.event.cached_default_tax_rule or TaxRule.zero()
                else:
                    payment_fee_tax_rule = TaxRule.zero()
                try:
                    payment_fee_tax = payment_fee_tax_rule.tax(payment_fee, base_price_is='gross', invoice_address=invoice_address)
                except TaxRule.SaleNotAllowed:
                    # Replicate behavior from elsewhere, will fail later at the order stage
                    payment_fee = Decimal("0.00")
                    payment_fee_tax = TaxRule.zero().tax(payment_fee)
                pf = OrderFee(
                    fee_type=OrderFee.FEE_TYPE_PAYMENT,
                    value=payment_fee,
                    tax_rate=payment_fee_tax.rate,
                    tax_value=payment_fee_tax.tax,
                    tax_code=payment_fee_tax.code,
                    tax_rule=payment_fee_tax_rule
                )
                fees.append(pf)

                # Re-apply rounding as grand total has changed
                apply_rounding(self.request.event.settings.tax_rounding, invoice_address, self.request.event.currency, [*positions, *fees])
                total = sum([c.price for c in positions]) + sum([f.value for f in fees])

                # Re-calculate to_pay as grand total has changed
                to_pay = max(total - payments_assigned, Decimal("0.00"))
                if p.get('max_value') and to_pay > Decimal(p['max_value']):
                    to_pay = min(to_pay, Decimal(p['max_value']))

            if p.get('max_value') and to_pay > Decimal(p['max_value']):
                to_pay = min(to_pay, Decimal(p['max_value']))

            p['payment_amount'] = to_pay
            p['provider_name'] = pprov.public_name
            p['pprov'] = pprov
            p['fee'] = payment_fee
            payments_assigned += to_pay
            payments.append(p)
        return payments

    def _remove_payment(self, payment_id):
        self.cart_session['payments'] = [p for p in self.cart_session['payments'] if p.get('id') != payment_id]


def cart_exists(request):
    from pretix.presale.views.cart import get_or_create_cart_id

    if not hasattr(request, '_cart_cache'):
        return CartPosition.objects.filter(
            cart_id=get_or_create_cart_id(request), event=request.event
        ).exists()
    return bool(request._cart_cache)


def get_cart(request):
    from pretix.presale.views.cart import get_or_create_cart_id

    if not hasattr(request, '_cart_cache'):
        cart_id = get_or_create_cart_id(request, create=False)
        if not cart_id:
            request._cart_cache = CartPosition.objects.none()
        else:
            qqs = request.event.questions.all()
            qqs = qqs.filter(ask_during_checkin=False, hidden=False)
            request._cart_cache = CartPosition.objects.filter(
                cart_id=cart_id, event=request.event
            ).annotate(
                has_addon_choices=Exists(
                    ItemAddOn.objects.filter(
                        base_item_id=OuterRef('item_id')
                    )
                )
            ).order_by(
                'item__category__position', 'item__category_id', 'item__position', 'item__name', 'variation__value'
            ).select_related(
                'item', 'variation', 'subevent', 'subevent__event', 'subevent__event__organizer',
                'item__tax_rule', 'item__category', 'used_membership', 'used_membership__membership_type'
            ).select_related(
                'addon_to'
            ).prefetch_related(
                'addons', 'addons__item', 'addons__variation',
                Prefetch('answers',
                         QuestionAnswer.objects.prefetch_related('options'),
                         to_attr='answerlist'),
                Prefetch('item__questions',
                         qqs.prefetch_related(
                             Prefetch('options', QuestionOption.objects.prefetch_related(Prefetch(
                                 # This prefetch statement is utter bullshit, but it actually prevents Django from doing
                                 # a lot of queries since ModelChoiceIterator stops trying to be clever once we have
                                 # a prefetch lookup on this query...
                                 'question',
                                 Question.objects.none(),
                                 to_attr='dummy'
                             )))
                         ).select_related('dependency_question'),
                         to_attr='questions_to_ask')
            )
            by_id = {cp.pk: cp for cp in request._cart_cache}
            for cp in request._cart_cache:
                # Populate fields with known values to save queries
                cp.event = request.event
                if cp.addon_to_id:
                    cp.addon_to = by_id[cp.addon_to_id]
    return request._cart_cache


def get_cart_total(request):
    """
    Use the following pattern instead::

        cart = get_cart(request)
        fees = get_fees(
            event=request.event,
            request=request,
            invoice_address=cached_invoice_address(request),
            payments=None,
            positions=cart,
        )
        total = sum([c.price for c in cart]) + sum([f.value for f in fees])
    """
    warnings.warn('get_cart_total is deprecated and will be removed in a future release',
                  DeprecationWarning)
    from pretix.presale.views.cart import get_or_create_cart_id

    if not hasattr(request, '_cart_total_cache'):
        if hasattr(request, '_cart_cache'):
            request._cart_total_cache = sum(i.price for i in request._cart_cache)
        else:
            request._cart_total_cache = CartPosition.objects.filter(
                cart_id=get_or_create_cart_id(request), event=request.event
            ).aggregate(sum=Sum('price'))['sum'] or Decimal('0.00')
    return request._cart_total_cache


def get_cart_invoice_address(request):
    from pretix.presale.views.cart import cart_session

    if not hasattr(request, '_checkout_flow_invoice_address'):
        cs = cart_session(request)
        iapk = cs.get('invoice_address')
        if not iapk:
            request._checkout_flow_invoice_address = InvoiceAddress()
        else:
            try:
                with scopes_disabled():
                    request._checkout_flow_invoice_address = InvoiceAddress.objects.get(pk=iapk, order__isnull=True)
            except InvoiceAddress.DoesNotExist:
                request._checkout_flow_invoice_address = InvoiceAddress()
    return request._checkout_flow_invoice_address


def get_cart_is_free(request):
    from pretix.presale.views.cart import cart_session

    if not hasattr(request, '_cart_free_cache'):
        cs = cart_session(request)
        pos = get_cart(request)
        ia = get_cart_invoice_address(request)
        try:
            fees = get_fees(event=request.event, request=request, invoice_address=ia,
                            payments=cs.get('payments', []), positions=pos)
        except TaxRule.SaleNotAllowed:
            # ignore for now, will fail on order creation
            fees = []

        request._cart_free_cache = sum(p.price for p in pos) + sum(f.value for f in fees) == Decimal('0.00')
    return request._cart_free_cache


class EventViewMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['event'] = self.request.event
        return context

    def get_index_url(self):
        kwargs = {}
        if 'cart_namespace' in self.kwargs:
            kwargs['cart_namespace'] = self.kwargs['cart_namespace']
        return eventreverse(self.request.event, 'presale:event.index', kwargs=kwargs)


class OrganizerViewMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['organizer'] = self.request.organizer
        return context


def allow_frame_if_namespaced(view_func):
    """
    Drop X-Frame-Options header, but only if a cart namespace is set. See get_or_create_cart_id()
    for the reasoning.
    """
    def wrapped_view(request, *args, **kwargs):
        resp = view_func(request, *args, **kwargs)
        if request.resolver_match and request.resolver_match.kwargs.get('cart_namespace'):
            resp.xframe_options_exempt = True
        return resp
    return wraps(view_func)(wrapped_view)


def allow_cors_if_namespaced(view_func):
    """
    Add Access-Control-Allow-Origin header, but only if a cart namespace is set.
    See get_or_create_cart_id() for the reasoning.
    """
    def wrapped_view(request, *args, **kwargs):
        resp = view_func(request, *args, **kwargs)
        if request.resolver_match and request.resolver_match.kwargs.get('cart_namespace'):
            resp['Access-Control-Allow-Origin'] = '*'
        return resp
    return wraps(view_func)(wrapped_view)


def iframe_entry_view_wrapper(view_func):
    def wrapped_view(request, *args, **kwargs):
        if 'iframe' in request.GET:
            request.session['iframe_session'] = True

        if request.GET.get("consent"):
            request.session["requested_consent_from_widget"] = request.GET["consent"]

        locale = request.GET.get('locale')
        if locale and locale in [lc for lc, ll in settings.LANGUAGES]:
            lng = locale
            if hasattr(request, 'event'):
                lng = get_supported_language(
                    lng,
                    request.event.settings.locales,
                    request.event.settings.locale,
                )

                region = request.event.settings.region
                if '-' not in lng and region:
                    lng += '-' + region.lower()
                set_region(region)

            # with language() is not good enough here – we really need to take the role of LocaleMiddleware and modify
            # global state, because template rendering might be happening lazily.
            translation.activate(lng)
            request.LANGUAGE_CODE = get_language_without_region()
            resp = view_func(request, *args, **kwargs)

            max_age = 10 * 365 * 24 * 60 * 60
            set_cookie_without_samesite(
                request,
                resp,
                settings.LANGUAGE_COOKIE_NAME,
                locale,
                max_age=max_age,
                expires=(datetime.utcnow() + timedelta(seconds=max_age)).strftime('%a, %d-%b-%Y %H:%M:%S GMT'),
            )
            return resp

        resp = view_func(request, *args, **kwargs)
        return resp
    return wraps(view_func)(wrapped_view)
