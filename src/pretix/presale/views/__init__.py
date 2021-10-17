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
# This file contains Apache-licensed contributions copyrighted by: Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from functools import wraps
from itertools import groupby

from django.conf import settings
from django.db.models import Exists, OuterRef, Prefetch, Sum
from django.utils.functional import cached_property
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.i18n import language
from pretix.base.models import (
    CartPosition, Customer, InvoiceAddress, ItemAddOn, OrderPosition, Question,
    QuestionAnswer, QuestionOption,
)
from pretix.base.services.cart import get_fees
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

    def get_cart(self, answers=False, queryset=None, order=None, downloads=False):
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

        # Group items of the same variation
        # We do this by list manipulations instead of a GROUP BY query, as
        # Django is unable to join related models in a .values() query
        def keyfunc(pos):
            if isinstance(pos, OrderPosition):
                if pos.addon_to_id:
                    i = pos.addon_to.positionid
                else:
                    i = pos.positionid
            else:
                if pos.addon_to_id:
                    i = pos.addon_to_id
                else:
                    i = pos.pk

            has_attendee_data = pos.item.admission and (
                self.request.event.settings.attendee_names_asked
                or self.request.event.settings.attendee_emails_asked
                or pos_additional_fields.get(pos.pk)
            )

            addon_penalty = 1 if pos.addon_to_id else 0

            if downloads \
                    or pos.pk in has_addons \
                    or pos.addon_to_id \
                    or pos.item.issue_giftcard \
                    or (answers and (has_attendee_data or bool(pos.item.questions.all()))):  # do not use .exists() to re-use prefetch cache
                return (
                    # standalone positions are grouped by main product position id, addons below them also sorted by position id
                    i, addon_penalty, pos.pk,
                    # all other places are only used for positions that can be grouped. We just put zeros.
                ) + (0, ) * 10

            # positions are sorted and grouped by various attributes
            category_key = (pos.item.category.position, pos.item.category.id) if pos.item.category is not None else (0, 0)
            item_key = pos.item.position, pos.item_id
            variation_key = (pos.variation.position, pos.variation.id) if pos.variation is not None else (0, 0)
            return (
                # These are grouped by attributes so we don't put any position ids
                0, 0, 0,
            ) + category_key + item_key + variation_key + (pos.price, (pos.voucher_id or 0), (pos.subevent_id or 0), (pos.seat_id or 0))

        positions = []
        for k, g in groupby(sorted(lcp, key=keyfunc), key=keyfunc):
            g = list(g)
            group = g[0]
            group.count = len(g)
            group.total = group.count * group.price
            group.net_total = group.count * group.net_price
            group.has_questions = answers and k[0] != ""
            if not hasattr(group, 'tax_rule'):
                group.tax_rule = group.item.tax_rule

            group.bundle_sum = group.price + sum(a.price for a in has_addons[group.pk])
            group.bundle_sum_net = group.net_price + sum(a.net_price for a in has_addons[group.pk])

            if answers:
                group.cache_answers(all=False)
                group.additional_answers = pos_additional_fields.get(group.pk)
            positions.append(group)

        total = sum(p.total for p in positions)
        net_total = sum(p.net_total for p in positions)
        tax_total = sum(p.total - p.net_total for p in positions)

        if order:
            fees = order.fees.all()
        elif positions:
            fees = get_fees(
                self.request.event, self.request, total, self.invoice_address, self.cart_session.get('payment'),
                cartpos
            )
        else:
            fees = []

        total += sum([f.value for f in fees])
        net_total += sum([f.net_value for f in fees])
        tax_total += sum([f.tax_value for f in fees])

        try:
            first_expiry = min(p.expires for p in positions) if positions else now()
            total_seconds_left = max(first_expiry - now(), timedelta()).total_seconds()
            minutes_left = int(total_seconds_left // 60)
            seconds_left = int(total_seconds_left % 60)
        except AttributeError:
            first_expiry = None
            minutes_left = None
            seconds_left = None

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
            'is_ordered': bool(order),
            'itemcount': sum(c.count for c in positions if not c.addon_to)
        }


def cart_exists(request):
    from pretix.presale.views.cart import get_or_create_cart_id

    if not hasattr(request, '_cart_cache'):
        return CartPosition.objects.filter(
            cart_id=get_or_create_cart_id(request), event=request.event
        ).exists()
    return bool(request._cart_cache)


def get_cart(request):
    from pretix.presale.views.cart import get_or_create_cart_id
    qqs = request.event.questions.all()
    qqs = qqs.filter(ask_during_checkin=False, hidden=False)

    if not hasattr(request, '_cart_cache'):
        cart_id = get_or_create_cart_id(request, create=False)
        if not cart_id:
            request._cart_cache = CartPosition.objects.none()
        else:
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
                'item__tax_rule', 'addon_to', 'used_membership', 'used_membership__membership_type'
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
            for cp in request._cart_cache:
                cp.event = request.event  # Populate field with known value to save queries
    return request._cart_cache


def get_cart_total(request):
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
        total = get_cart_total(request)
        fees = get_fees(request.event, request, total, ia, cs.get('payment'), pos)
        request._cart_free_cache = total + sum(f.value for f in fees) == Decimal('0.00')
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

        locale = request.GET.get('locale')
        if locale and locale in [lc for lc, ll in settings.LANGUAGES]:
            region = None
            if hasattr(request, 'event'):
                region = request.event.settings.region
            with language(locale, region):
                resp = view_func(request, *args, **kwargs)
            max_age = 10 * 365 * 24 * 60 * 60
            set_cookie_without_samesite(
                request,
                resp,
                settings.LANGUAGE_COOKIE_NAME,
                locale,
                max_age=max_age,
                expires=(datetime.utcnow() + timedelta(seconds=max_age)).strftime('%a, %d-%b-%Y %H:%M:%S GMT'),
                domain=settings.SESSION_COOKIE_DOMAIN
            )
            return resp

        resp = view_func(request, *args, **kwargs)
        return resp
    return wraps(view_func)(wrapped_view)
