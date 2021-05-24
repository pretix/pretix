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
import copy
import inspect
from collections import defaultdict
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db.models import F, Q
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import redirect
from django.utils import translation
from django.utils.functional import cached_property
from django.utils.translation import (
    get_language, gettext_lazy as _, pgettext_lazy,
)
from django.views.generic.base import TemplateResponseMixin
from django_scopes import scopes_disabled

from pretix.base.models import Customer, Order
from pretix.base.models.orders import InvoiceAddress, OrderPayment
from pretix.base.models.tax import TaxedPrice, TaxRule
from pretix.base.services.cart import (
    CartError, error_messages, get_fees, set_cart_addons, update_tax_rates,
)
from pretix.base.services.memberships import validate_memberships_in_order
from pretix.base.services.orders import perform_order
from pretix.base.settings import PERSON_NAME_SCHEMES
from pretix.base.signals import validate_cart_addons
from pretix.base.templatetags.phone_format import phone_format
from pretix.base.templatetags.rich_text import rich_text_snippet
from pretix.base.views.tasks import AsyncAction
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.forms.checkout import (
    ContactForm, InvoiceAddressForm, InvoiceNameForm, MembershipForm,
)
from pretix.presale.forms.customer import AuthenticationForm, RegistrationForm
from pretix.presale.signals import (
    checkout_all_optional, checkout_confirm_messages, checkout_flow_steps,
    contact_form_fields, contact_form_fields_overrides,
    order_meta_from_request, question_form_fields,
    question_form_fields_overrides,
)
from pretix.presale.utils import customer_login
from pretix.presale.views import (
    CartMixin, get_cart, get_cart_is_free, get_cart_total,
)
from pretix.presale.views.cart import (
    cart_session, create_empty_cart_id, get_or_create_cart_id,
)
from pretix.presale.views.event import get_grouped_items
from pretix.presale.views.questions import QuestionsViewMixin


class BaseCheckoutFlowStep:
    requires_valid_cart = True
    icon = 'pencil'

    def __init__(self, event):
        self.event = event
        self.request = None

    @property
    def identifier(self):
        raise NotImplementedError()

    @property
    def label(self):
        return pgettext_lazy('checkoutflow', 'Step')

    @property
    def priority(self):
        return 100

    def is_applicable(self, request):
        return True

    def is_completed(self, request, warn=False):
        raise NotImplementedError()

    def get_next_applicable(self, request):
        if hasattr(self, '_next') and self._next:
            if not self._next.is_applicable(request):
                return self._next.get_next_applicable(request)
            return self._next

    def get_prev_applicable(self, request):
        if hasattr(self, '_previous') and self._previous:
            if not self._previous.is_applicable(request):
                return self._previous.get_prev_applicable(request)
            return self._previous

    def get(self, request):
        return HttpResponseNotAllowed([])

    def post(self, request):
        return HttpResponseNotAllowed([])

    def get_step_url(self, request):
        kwargs = {'step': self.identifier}
        if request.resolver_match and 'cart_namespace' in request.resolver_match.kwargs:
            kwargs['cart_namespace'] = request.resolver_match.kwargs['cart_namespace']
        return eventreverse(self.event, 'presale:event.checkout', kwargs=kwargs)

    def get_prev_url(self, request):
        prev = self.get_prev_applicable(request)
        if not prev:
            kwargs = {}
            if request.resolver_match and 'cart_namespace' in request.resolver_match.kwargs:
                kwargs['cart_namespace'] = request.resolver_match.kwargs['cart_namespace']
            return eventreverse(self.request.event, 'presale:event.index', kwargs=kwargs)
        else:
            return prev.get_step_url(request)

    def get_next_url(self, request):
        n = self.get_next_applicable(request)
        if n:
            return n.get_step_url(request)

    @cached_property
    def cart_session(self):
        return cart_session(self.request)

    @cached_property
    def invoice_address(self):
        if not hasattr(self.request, '_checkout_flow_invoice_address'):
            iapk = self.cart_session.get('invoice_address')
            if not iapk:
                self.request._checkout_flow_invoice_address = InvoiceAddress()
            else:
                try:
                    with scopes_disabled():
                        self.request._checkout_flow_invoice_address = InvoiceAddress.objects.get(
                            pk=iapk, order__isnull=True
                        )
                except InvoiceAddress.DoesNotExist:
                    self.request._checkout_flow_invoice_address = InvoiceAddress()
        return self.request._checkout_flow_invoice_address


def get_checkout_flow(event):
    flow = list([step(event) for step in DEFAULT_FLOW])
    for receiver, response in checkout_flow_steps.send(event):
        step = response(event=event)
        if step.priority > 1000:
            raise ValueError('Plugins are not allowed to define a priority greater than 1000')
        flow.append(step)

    # Sort by priority
    flow.sort(key=lambda p: p.priority)

    # Create a double-linked-list for easy forwards/backwards traversal
    last = None
    for step in flow:
        step._previous = last
        if last:
            last._next = step
        last = step
    return flow


class TemplateFlowStep(TemplateResponseMixin, BaseCheckoutFlowStep):
    template_name = ""

    def get_context_data(self, **kwargs):
        kwargs.setdefault('step', self)
        kwargs.setdefault('event', self.event)
        kwargs.setdefault('has_prev', self.get_prev_applicable(self.request) is not None)
        kwargs.setdefault('prev_url', self.get_prev_url(self.request))
        kwargs.setdefault('checkout_flow', [
            step
            for step in self.request._checkout_flow
            if step.is_applicable(self.request)
        ])
        return kwargs

    def render(self, **kwargs):
        context = self.get_context_data(**kwargs)
        return self.render_to_response(context)

    def get(self, request):
        self.request = request
        return self.render()

    def post(self, request):
        self.request = request
        return self.render()

    def is_completed(self, request, warn=False):
        raise NotImplementedError()

    @property
    def identifier(self):
        raise NotImplementedError()


class CustomerStep(CartMixin, TemplateFlowStep):
    priority = 45
    identifier = "customer"
    template_name = "pretixpresale/event/checkout_customer.html"
    label = pgettext_lazy('checkoutflow', 'Customer account')
    icon = 'user'

    def is_applicable(self, request):
        return request.organizer.settings.customer_accounts

    @cached_property
    def login_form(self):
        f = AuthenticationForm(
            data=(
                self.request.POST
                if self.request.method == "POST" and self.request.POST.get('customer_mode') == 'login'
                else None
            ),
            prefix='login',
            request=self.request.event,
        )
        for field in f.fields.values():
            field._show_required = field.required
            field.required = False
            field.widget.is_required = False
        return f

    @cached_property
    def signup_allowed(self):
        return not any(
            p.item.require_membership or
            (p.variation and p.variation.require_membership)
            for p in self.positions
        )

    @cached_property
    def guest_allowed(self):
        return not any(
            p.item.require_membership or
            (p.variation and p.variation.require_membership) or
            p.item.grant_membership_type_id
            for p in self.positions
        )

    @cached_property
    def register_form(self):
        f = RegistrationForm(
            data=(
                self.request.POST
                if self.request.method == "POST" and self.request.POST.get('customer_mode') == 'register'
                else None
            ),
            prefix='register',
            request=self.request,
        )
        for field in f.fields.values():
            field._show_required = field.required
            field.required = False
            field.widget.is_required = False
        return f

    def post(self, request):
        self.request = request

        if request.POST.get("customer_mode") == 'login':
            if self.cart_session.get('customer'):
                return redirect(self.get_next_url(request))
            elif request.customer:
                self.cart_session['customer_mode'] = 'login'
                self.cart_session['customer'] = request.customer.pk
                return redirect(self.get_next_url(request))
            elif self.login_form.is_valid():
                customer_login(self.request, self.login_form.get_customer())
                self.cart_session['customer_mode'] = 'login'
                self.cart_session['customer'] = self.login_form.get_customer().pk
                return redirect(self.get_next_url(request))
            else:
                return self.render()
        elif request.POST.get("customer_mode") == 'register':
            if self.register_form.is_valid():
                customer = self.register_form.create()
                self.cart_session['customer_mode'] = 'login'
                self.cart_session['customer'] = customer.pk
                return redirect(self.get_next_url(request))
            else:
                return self.render()
        elif request.POST.get("customer_mode") == 'guest' and self.guest_allowed:
            self.cart_session['customer'] = None
            self.cart_session['customer_mode'] = 'guest'
            return redirect(self.get_next_url(request))
        else:
            return self.render()

    def is_completed(self, request, warn=False):
        self.request = request
        if self.guest_allowed:
            return 'customer_mode' in self.cart_session
        else:
            return self.cart_session.get('customer_mode') == 'login'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['cart'] = self.get_cart()
        ctx['cart_session'] = self.cart_session
        ctx['login_form'] = self.login_form
        ctx['register_form'] = self.register_form
        ctx['selected'] = self.request.POST.get(
            'customer_mode',
            self.cart_session.get('customer_mode', 'login' if self.request.customer else '')
        )
        ctx['guest_allowed'] = self.guest_allowed
        ctx['signup_allowed'] = self.signup_allowed

        if 'customer' in self.cart_session:
            try:
                ctx['customer'] = self.request.organizer.customers.get(pk=self.cart_session.get('customer', -1))
            except Customer.DoesNotExist:
                self.cart_session['customer'] = None
                self.cart_session['customer_mode'] = None
        elif self.request.customer:
            ctx['customer'] = self.request.customer

        return ctx


class MembershipStep(CartMixin, TemplateFlowStep):
    priority = 47
    identifier = "membership"
    template_name = "pretixpresale/event/checkout_membership.html"
    label = pgettext_lazy('checkoutflow', 'Membership')
    icon = 'id-card'

    def is_applicable(self, request):
        self.request = request
        return bool(self.applicable_positions)

    @cached_property
    def applicable_positions(self):
        return [
            p for p in self.positions
            if p.item.require_membership or (p.variation and p.variation.require_membership)
        ]

    @cached_property
    def forms(self):
        forms = []

        memberships = list(self.cart_customer.memberships.with_usages().filter(
            Q(Q(membership_type__max_usages__isnull=True) | Q(usages__lt=F('membership_type__max_usages'))),
            canceled=False
        ).select_related('membership_type'))

        for p in self.applicable_positions:
            form = MembershipForm(
                event=self.request.event,
                memberships=memberships,
                position=p,
                prefix=f"membership-{p.id}",
                initial={
                    'membership': str(p.used_membership_id)
                },
                data=self.request.POST if self.request.method == "POST" else None,
            )
            forms.append(form)

        return forms

    def post(self, request):
        self.request = request

        for f in self.forms:
            if not f.is_valid():
                messages.error(request, _('Your cart includes a product that requires an active membership to be selected.'))
                return self.render()

            f.position.used_membership = f.cleaned_data['membership']

        try:
            validate_memberships_in_order(self.cart_customer, self.positions, self.request.event, lock=False, testmode=self.request.event.testmode)
        except ValidationError as e:
            messages.error(self.request, e.message)
            self.render()
        else:
            for f in self.forms:
                f.position.save(update_fields=['used_membership'])

        return redirect(self.get_next_url(request))

    def is_completed(self, request, warn=False):
        self.request = request
        ok = all([p.used_membership_id for p in self.applicable_positions])
        if not ok and warn:
            messages.error(request, _('Your cart includes a product that requires an active membership to be selected.'))
        return ok

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['cart'] = self.get_cart()
        ctx['cart_session'] = self.cart_session
        ctx['forms'] = self.forms

        return ctx


class AddOnsStep(CartMixin, AsyncAction, TemplateFlowStep):
    priority = 40
    identifier = "addons"
    template_name = "pretixpresale/event/checkout_addons.html"
    task = set_cart_addons
    known_errortypes = ['CartError']
    requires_valid_cart = False
    label = pgettext_lazy('checkoutflow', 'Add-on products')
    icon = 'puzzle-piece'

    def is_applicable(self, request):
        if not hasattr(request, '_checkoutflow_addons_applicable'):
            request._checkoutflow_addons_applicable = get_cart(request).filter(item__addons__isnull=False).exists()
        return request._checkoutflow_addons_applicable

    def is_completed(self, request, warn=False):
        if getattr(self, '_completed', None) is not None:
            return self._completed
        for cartpos in get_cart(request).filter(addon_to__isnull=True).prefetch_related(
            'item__addons', 'item__addons__addon_category', 'addons', 'addons__item'
        ):
            a = cartpos.addons.all()
            for iao in cartpos.item.addons.all():
                found = len([1 for p in a if p.item.category_id == iao.addon_category_id and not p.is_bundled])
                if found < iao.min_count or found > iao.max_count:
                    self._completed = False
                    return False
        self._completed = True
        return True

    @cached_property
    def forms(self):
        """
        A list of forms with one form for each cart position that can have add-ons.
        All forms have a custom prefix, so that they can all be submitted at once.
        """
        formset = []
        quota_cache = {}
        item_cache = {}
        for cartpos in get_cart(self.request).filter(addon_to__isnull=True).prefetch_related(
            'item__addons', 'item__addons__addon_category', 'addons', 'addons__variation',
        ).order_by('pk'):
            formsetentry = {
                'cartpos': cartpos,
                'item': cartpos.item,
                'variation': cartpos.variation,
                'categories': []
            }
            formset.append(formsetentry)

            current_addon_products = defaultdict(list)
            for a in cartpos.addons.all():
                if not a.is_bundled:
                    current_addon_products[a.item_id, a.variation_id].append(a)

            for iao in cartpos.item.addons.all():
                ckey = '{}-{}'.format(cartpos.subevent.pk if cartpos.subevent else 0, iao.addon_category.pk)

                if ckey not in item_cache:
                    # Get all items to possibly show
                    items, _btn = get_grouped_items(
                        self.request.event,
                        subevent=cartpos.subevent,
                        voucher=None,
                        channel=self.request.sales_channel.identifier,
                        base_qs=iao.addon_category.items,
                        allow_addons=True,
                        quota_cache=quota_cache
                    )
                    item_cache[ckey] = items
                else:
                    items = item_cache[ckey]

                for i in items:
                    i.allow_waitinglist = False

                    if i.has_variations:
                        for v in i.available_variations:
                            v.initial = len(current_addon_products[i.pk, v.pk])
                            if v.initial and i.free_price:
                                a = current_addon_products[i.pk, v.pk][0]
                                v.initial_price = TaxedPrice(
                                    net=a.price - a.tax_value,
                                    gross=a.price,
                                    tax=a.tax_value,
                                    name=a.item.tax_rule.name if a.item.tax_rule else "",
                                    rate=a.tax_rate,
                                )
                            else:
                                v.initial_price = v.display_price
                        i.expand = any(v.initial for v in i.available_variations)
                    else:
                        i.initial = len(current_addon_products[i.pk, None])
                        if i.initial and i.free_price:
                            a = current_addon_products[i.pk, None][0]
                            i.initial_price = TaxedPrice(
                                net=a.price - a.tax_value,
                                gross=a.price,
                                tax=a.tax_value,
                                name=a.item.tax_rule.name if a.item.tax_rule else "",
                                rate=a.tax_rate,
                            )
                        else:
                            i.initial_price = i.display_price

                if items:
                    formsetentry['categories'].append({
                        'category': iao.addon_category,
                        'price_included': iao.price_included,
                        'multi_allowed': iao.multi_allowed,
                        'min_count': iao.min_count,
                        'max_count': iao.max_count,
                        'iao': iao,
                        'items': items
                    })
        return formset

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['forms'] = self.forms
        ctx['cart'] = self.get_cart()
        return ctx

    def get_success_message(self, value):
        return None

    def get_success_url(self, value):
        return self.get_next_url(self.request)

    def get_error_url(self):
        return self.get_step_url(self.request)

    def get(self, request, **kwargs):
        self.request = request
        if 'async_id' in request.GET and settings.HAS_CELERY:
            return self.get_result(request)
        return TemplateFlowStep.get(self, request)

    def _clean_category(self, form, category):
        selected = {}
        for i in category['items']:
            if i.has_variations:
                for v in i.available_variations:
                    val = int(self.request.POST.get(f'cp_{form["cartpos"].pk}_variation_{i.pk}_{v.pk}') or '0')
                    price = self.request.POST.get(f'cp_{form["cartpos"].pk}_variation_{i.pk}_{v.pk}_price') or '0'
                    if val:
                        selected[i, v] = val, price
            else:
                val = int(self.request.POST.get(f'cp_{form["cartpos"].pk}_item_{i.pk}') or '0')
                price = self.request.POST.get(f'cp_{form["cartpos"].pk}_item_{i.pk}_price') or '0'
                if val:
                    selected[i, None] = val, price

        if sum(a[0] for a in selected.values()) > category['max_count']:
            # TODO: Proper pluralization
            raise ValidationError(
                _(error_messages['addon_max_count']),
                'addon_max_count',
                {
                    'base': str(form['item'].name),
                    'max': category['max_count'],
                    'cat': str(category['category'].name),
                }
            )
        elif sum(a[0] for a in selected.values()) < category['min_count']:
            # TODO: Proper pluralization
            raise ValidationError(
                _(error_messages['addon_min_count']),
                'addon_min_count',
                {
                    'base': str(form['item'].name),
                    'min': category['min_count'],
                    'cat': str(category['category'].name),
                }
            )
        elif any(sum(v[0] for k, v in selected.items() if k[0] == i) > 1 for i in category['items']) and not category['multi_allowed']:
            raise ValidationError(
                _(error_messages['addon_no_multi']),
                'addon_no_multi',
                {
                    'base': str(form['item'].name),
                    'cat': str(category['category'].name),
                }
            )
        try:
            validate_cart_addons.send(
                sender=self.event,
                addons={k: v[0] for k, v in selected.items()},
                base_position=form["cartpos"],
                iao=category['iao']
            )
        except CartError as e:
            raise ValidationError(str(e))

        return selected

    def post(self, request, *args, **kwargs):
        self.request = request
        data = []
        for f in self.forms:
            for c in f['categories']:
                try:
                    selected = self._clean_category(f, c)
                except ValidationError as e:
                    messages.error(request, e.message % e.params if e.params else e.message)
                    return self.get(request, *args, **kwargs)

                for (i, v), (c, price) in selected.items():
                    data.append({
                        'addon_to': f['cartpos'].pk,
                        'item': i.pk,
                        'variation': v.pk if v else None,
                        'count': c,
                        'price': price,
                    })

        return self.do(self.request.event.id, data, get_or_create_cart_id(self.request),
                       invoice_address=self.invoice_address.pk, locale=get_language(),
                       sales_channel=request.sales_channel.identifier)


class QuestionsStep(QuestionsViewMixin, CartMixin, TemplateFlowStep):
    priority = 50
    identifier = "questions"
    template_name = "pretixpresale/event/checkout_questions.html"
    label = pgettext_lazy('checkoutflow', 'Your information')

    def is_applicable(self, request):
        return True

    @cached_property
    def all_optional(self):
        for recv, resp in checkout_all_optional.send(sender=self.request.event, request=self.request):
            if resp:
                return True
        return False

    @cached_property
    def _contact_override_sets(self):
        return [
            resp for recv, resp in contact_form_fields_overrides.send(
                self.request.event,
                request=self.request,
                order=None,
            )
        ]

    @cached_property
    def contact_form(self):
        wd = self.cart_session.get('widget_data', {})
        initial = {
            'email': (
                self.cart_session.get('email', '') or
                wd.get('email', '')
            ),
            'phone': wd.get('phone', None)
        }
        initial.update(self.cart_session.get('contact_form_data', {}))

        override_sets = self._contact_override_sets
        for overrides in override_sets:
            initial.update({
                k: v['initial'] for k, v in overrides.items() if 'initial' in v
            })
        if self.cart_customer:
            initial['email'] = self.cart_customer.email

        f = ContactForm(data=self.request.POST if self.request.method == "POST" else None,
                        event=self.request.event,
                        request=self.request,
                        initial=initial, all_optional=self.all_optional)
        if wd.get('email', '') and wd.get('fix', '') == "true" or self.cart_customer:
            f.fields['email'].disabled = True

        for overrides in override_sets:
            for fname, val in overrides.items():
                if 'disabled' in val and fname in f.fields:
                    f.fields[fname].disabled = val['disabled']
                if 'validators' in val and fname in f.fields:
                    f.fields[fname].validators += val['validators']

        return f

    def get_question_override_sets(self, cart_position):
        o = []
        if self.cart_customer:
            o.append({
                'attendee_name_parts': {
                    'initial': self.cart_customer.name_parts
                }
            })
        o += [
            resp for recv, resp in question_form_fields_overrides.send(
                self.request.event,
                position=cart_position,
                request=self.request
            )
        ]
        if cart_position.used_membership:
            d = {
                'initial': cart_position.used_membership.attendee_name_parts
            }
            if not cart_position.used_membership.membership_type.transferable:
                d['disabled'] = True
            o.append({
                'attendee_name_parts': d
            })

        return o

    @cached_property
    def eu_reverse_charge_relevant(self):
        return any([p.item.tax_rule and (p.item.tax_rule.eu_reverse_charge or p.item.tax_rule.custom_rules)
                    for p in self.positions])

    @cached_property
    def invoice_form(self):
        wd = self.cart_session.get('widget_data', {})
        if not self.invoice_address.pk:
            wd_initial = {
                'name_parts': {
                    k[21:].replace('-', '_'): v
                    for k, v in wd.items()
                    if k.startswith('invoice-address-name-')
                },
                'company': wd.get('invoice-address-company', ''),
                'is_business': bool(wd.get('invoice-address-company', '')),
                'street': wd.get('invoice-address-street', ''),
                'zipcode': wd.get('invoice-address-zipcode', ''),
                'city': wd.get('invoice-address-city', ''),
                'country': wd.get('invoice-address-country', ''),
            }
        else:
            wd_initial = {}
        initial = dict(wd_initial)

        if self.cart_customer:
            initial.update({
                'name_parts': self.cart_customer.name_parts
            })

            if 'saved_invoice_address' in self.cart_session:
                initial['saved_id'] = self.cart_session['saved_invoice_address']

        override_sets = self._contact_override_sets
        for overrides in override_sets:
            initial.update({
                k: v['initial'] for k, v in overrides.items() if 'initial' in v
            })

        if not self.address_asked and self.request.event.settings.invoice_name_required:
            f = InvoiceNameForm(data=self.request.POST if self.request.method == "POST" else None,
                                event=self.request.event,
                                request=self.request,
                                instance=self.invoice_address,
                                initial=initial,
                                validate_vat_id=False, all_optional=self.all_optional)
        else:
            f = InvoiceAddressForm(data=self.request.POST if self.request.method == "POST" else None,
                                   event=self.request.event,
                                   request=self.request,
                                   initial=initial,
                                   instance=self.invoice_address,
                                   allow_save=bool(self.cart_customer),
                                   validate_vat_id=self.eu_reverse_charge_relevant, all_optional=self.all_optional)
        for name, field in f.fields.items():
            if wd_initial.get(name) and wd.get('fix', '') == 'true':
                field.disabled = True

        for overrides in override_sets:
            for fname, val in overrides.items():
                if 'disabled' in val and fname in f.fields:
                    f.fields[fname].disabled = val['disabled']
                if 'validators' in val and fname in f.fields:
                    f.fields[fname].validators += val['validators']

        return f

    @cached_property
    def address_asked(self):
        return (
            self.request.event.settings.invoice_address_asked
            and (not self.request.event.settings.invoice_address_not_asked_free or not get_cart_is_free(self.request))
        )

    def post(self, request):
        self.request = request
        failed = not self.save() or not self.contact_form.is_valid()
        if self.address_asked or self.request.event.settings.invoice_name_required:
            failed = failed or not self.invoice_form.is_valid()
        if failed:
            messages.error(request,
                           _("We had difficulties processing your input. Please review the errors below."))
            return self.render()
        self.cart_session['email'] = self.contact_form.cleaned_data['email']
        d = dict(self.contact_form.cleaned_data)
        if d.get('phone'):
            d['phone'] = str(d['phone'])
        self.cart_session['contact_form_data'] = d
        if self.address_asked or self.request.event.settings.invoice_name_required:
            addr = self.invoice_form.save()

            if self.cart_customer and self.invoice_form.cleaned_data.get('save'):
                if self.invoice_form.cleaned_data.get('saved_id'):
                    saved = InvoiceAddress.profiles.filter(
                        customer=self.cart_customer, pk=self.invoice_form.cleaned_data.get('saved_id')
                    ).first() or InvoiceAddress(customer=self.cart_customer)
                else:
                    saved = InvoiceAddress(customer=self.cart_customer)

                for f in InvoiceAddress._meta.fields:
                    if f.name not in ('order', 'customer', 'last_modified', 'pk', 'id'):
                        val = getattr(addr, f.name)
                        setattr(saved, f.name, copy.deepcopy(val))

                saved.save()
                self.cart_session['saved_invoice_address'] = saved.pk

            try:
                diff = update_tax_rates(
                    event=request.event,
                    cart_id=get_or_create_cart_id(request),
                    invoice_address=addr
                )
            except TaxRule.SaleNotAllowed:
                messages.error(request,
                               _("Unfortunately, based on the invoice address you entered, we're not able to sell you "
                                 "the selected products for tax-related legal reasons."))
                return self.render()

            self.cart_session['invoice_address'] = addr.pk
            if abs(diff) > Decimal('0.001'):
                messages.info(request, _('Due to the invoice address you entered, we need to apply a different tax '
                                         'rate to your purchase and the price of the products in your cart has '
                                         'changed accordingly.'))
                return redirect(self.get_next_url(request) + '?open_cart=true')

        return redirect(self.get_next_url(request))

    def is_completed(self, request, warn=False):
        self.request = request
        try:
            emailval = EmailValidator()
            if not self.cart_session.get('email') and not self.all_optional:
                if warn:
                    messages.warning(request, _('Please enter a valid email address.'))
                return False
            if self.cart_session.get('email'):
                emailval(self.cart_session.get('email'))
        except ValidationError:
            if warn:
                messages.warning(request, _('Please enter a valid email address.'))
            return False

        if not self.all_optional:

            if self.address_asked:
                if request.event.settings.invoice_address_required and (not self.invoice_address or not self.invoice_address.street):
                    messages.warning(request, _('Please enter your invoicing address.'))
                    return False

            if request.event.settings.invoice_name_required and (not self.invoice_address or not self.invoice_address.name):
                messages.warning(request, _('Please enter your name.'))
                return False

        for cp in self._positions_for_questions:
            answ = {
                aw.question_id: aw for aw in cp.answerlist
            }
            question_cache = {
                q.pk: q for q in cp.item.questions_to_ask
            }

            def question_is_visible(parentid, qvals):
                if parentid not in question_cache:
                    return False
                parentq = question_cache[parentid]
                if parentq.dependency_question_id and not question_is_visible(parentq.dependency_question_id, parentq.dependency_values):
                    return False
                if parentid not in answ:
                    return False
                return (
                    ('True' in qvals and answ[parentid].answer == 'True')
                    or ('False' in qvals and answ[parentid].answer == 'False')
                    or (any(qval in [o.identifier for o in answ[parentid].options.all()] for qval in qvals))
                )

            def question_is_required(q):
                return (
                    q.required and
                    (not q.dependency_question_id or question_is_visible(q.dependency_question_id, q.dependency_values))
                )

            for q in cp.item.questions_to_ask:
                if question_is_required(q) and q.id not in answ:
                    if warn:
                        messages.warning(request, _('Please fill in answers to all required questions.'))
                    return False
            if cp.item.admission and self.request.event.settings.get('attendee_names_required', as_type=bool) \
                    and not cp.attendee_name_parts:
                if warn:
                    messages.warning(request, _('Please fill in answers to all required questions.'))
                return False
            if cp.item.admission and self.request.event.settings.get('attendee_emails_required', as_type=bool) \
                    and cp.attendee_email is None:
                if warn:
                    messages.warning(request, _('Please fill in answers to all required questions.'))
                return False
            if cp.item.admission and self.request.event.settings.get('attendee_company_required', as_type=bool) \
                    and cp.company is None:
                if warn:
                    messages.warning(request, _('Please fill in answers to all required questions.'))
                return False
            if cp.item.admission and self.request.event.settings.get('attendee_attendees_required', as_type=bool) \
                    and (cp.street is None or cp.city is None or cp.country is None):
                if warn:
                    messages.warning(request, _('Please fill in answers to all required questions.'))
                return False

            responses = question_form_fields.send(sender=self.request.event, position=cp)
            form_data = cp.meta_info_data.get('question_form_data', {})
            for r, response in sorted(responses, key=lambda r: str(r[0])):
                for key, value in response.items():
                    if value.required and not form_data.get(key):
                        return False
        return True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['formgroups'] = self.formdict.items()
        ctx['contact_form'] = self.contact_form
        ctx['invoice_form'] = self.invoice_form
        ctx['reverse_charge_relevant'] = self.eu_reverse_charge_relevant
        ctx['cart'] = self.get_cart()
        ctx['cart_session'] = self.cart_session
        ctx['invoice_address_asked'] = self.address_asked

        if self.cart_customer:
            ctx['addresses'] = self.cart_customer.stored_addresses.all()

            profiles = list(self.cart_customer.attendee_profiles.all())
            for form in self.forms:
                form.profiles = []
                for p in profiles:
                    data = {}

                    if p.attendee_name_parts:
                        scheme = PERSON_NAME_SCHEMES[self.request.event.settings.name_scheme]
                        for i, (k, l, w) in enumerate(scheme['fields']):
                            data[f'attendee_name_parts_{i}'] = p.attendee_name_parts.get(k) or ''

                    data.update({
                        'attendee_email': p.attendee_email,
                        'company': p.company,
                        'street': p.street,
                        'zipcode': p.zipcode,
                        'city': p.city,
                        'country': str(p.country) if p.country else None,
                        'state': str(p.state) if p.state else None,
                    })

                    for k, f in form.fields.items():
                        match_name = [a['value'] for a in p.answers if a['field_name'] == k]
                        match_identifier = [a['value'] for a in p.answers if hasattr(f, 'question') and a['question_identifier'] == f.question.identifier]
                        match_label = [a['value'] for a in p.answers if a['field_label'] == str(f.label)]
                        if match_name:
                            data[k] = match_name[0]
                        elif match_identifier:
                            data[k] = match_identifier[0]
                        elif match_label:
                            data[k] = match_label[0]

                    form.profiles.append((p, data))

            ctx['profiles'] = profiles

        return ctx


class PaymentStep(CartMixin, TemplateFlowStep):
    priority = 200
    identifier = "payment"
    template_name = "pretixpresale/event/checkout_payment.html"
    label = pgettext_lazy('checkoutflow', 'Payment')
    icon = 'credit-card'

    @cached_property
    def _total_order_value(self):
        cart = get_cart(self.request)
        total = get_cart_total(self.request)
        total += sum([f.value for f in get_fees(self.request.event, self.request, total, self.invoice_address, None,
                                                cart)])
        return Decimal(total)

    @cached_property
    def provider_forms(self):
        providers = []
        for provider in sorted(self.request.event.get_payment_providers().values(), key=lambda p: str(p.public_name)):
            if not provider.is_enabled or not self._is_allowed(provider, self.request):
                continue
            fee = provider.calculate_fee(self._total_order_value)
            if 'total' in inspect.signature(provider.payment_form_render).parameters:
                form = provider.payment_form_render(self.request, self._total_order_value + fee)
            else:
                form = provider.payment_form_render(self.request)
            providers.append({
                'provider': provider,
                'fee': fee,
                'total': self._total_order_value + fee,
                'form': form
            })
        return providers

    def post(self, request):
        self.request = request
        for p in self.provider_forms:
            if p['provider'].identifier == request.POST.get('payment', ''):
                self.cart_session['payment'] = p['provider'].identifier
                resp = p['provider'].checkout_prepare(
                    request,
                    self.get_cart()
                )
                if isinstance(resp, str):
                    return redirect(resp)
                elif resp is True:
                    return redirect(self.get_next_url(request))
                else:
                    return self.render()
        messages.error(self.request, _("Please select a payment method."))
        return self.render()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['providers'] = self.provider_forms
        ctx['show_fees'] = any(p['fee'] for p in self.provider_forms)
        ctx['selected'] = self.request.POST.get('payment', self.cart_session.get('payment', ''))
        if len(self.provider_forms) == 1:
            ctx['selected'] = self.provider_forms[0]['provider'].identifier
        ctx['cart'] = self.get_cart()
        return ctx

    @cached_property
    def payment_provider(self):
        return self.request.event.get_payment_providers().get(self.cart_session['payment'])

    def _is_allowed(self, prov, request):
        return prov.is_allowed(request, total=self._total_order_value)

    def is_completed(self, request, warn=False):
        self.request = request
        if 'payment' not in self.cart_session or not self.payment_provider:
            if warn:
                messages.error(request, _('The payment information you entered was incomplete.'))
            return False
        if not self.payment_provider.payment_is_valid_session(request) or \
                not self.payment_provider.is_enabled or \
                not self._is_allowed(self.payment_provider, request):
            if warn:
                messages.error(request, _('The payment information you entered was incomplete.'))
            return False
        return True

    def is_applicable(self, request):
        self.request = request

        for cartpos in get_cart(self.request):
            if cartpos.item.require_approval:
                if 'payment' in self.cart_session:
                    del self.cart_session['payment']
                return False

        for p in self.request.event.get_payment_providers().values():
            if p.is_implicit(request) if callable(p.is_implicit) else p.is_implicit:
                if self._is_allowed(p, request):
                    self.cart_session['payment'] = p.identifier
                    return False
                elif self.cart_session.get('payment') == p.identifier:
                    # is_allowed might have changed, e.g. after add-on selection
                    del self.cart_session['payment']

        return True


class ConfirmStep(CartMixin, AsyncAction, TemplateFlowStep):
    priority = 1001
    identifier = "confirm"
    template_name = "pretixpresale/event/checkout_confirm.html"
    task = perform_order
    known_errortypes = ['OrderError']
    label = pgettext_lazy('checkoutflow', 'Review order')
    icon = 'eye'

    def is_applicable(self, request):
        return True

    def is_completed(self, request, warn=False):
        pass

    @cached_property
    def address_asked(self):
        return (
            self.request.event.settings.invoice_address_asked
            and (not self.request.event.settings.invoice_address_not_asked_free or not get_cart_is_free(self.request))
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['cart'] = self.get_cart(answers=True)
        if self.payment_provider:
            ctx['payment'] = self.payment_provider.checkout_confirm_render(self.request)
            ctx['payment_provider'] = self.payment_provider
        ctx['require_approval'] = any(cp.item.require_approval for cp in ctx['cart']['positions'])
        ctx['addr'] = self.invoice_address
        ctx['confirm_messages'] = self.confirm_messages
        ctx['cart_session'] = self.cart_session
        ctx['invoice_address_asked'] = self.address_asked
        ctx['customer'] = self.cart_customer

        self.cart_session['shown_total'] = str(ctx['cart']['total'])

        email = self.cart_session.get('contact_form_data', {}).get('email')
        if email != settings.PRETIX_EMAIL_NONE_VALUE:
            ctx['contact_info'] = [
                (_('E-mail'), email),
            ]
        else:
            ctx['contact_info'] = []
        phone = self.cart_session.get('contact_form_data', {}).get('phone')
        if phone:
            ctx['contact_info'].append((_('Phone number'), phone_format(phone)))
        responses = contact_form_fields.send(self.event, request=self.request)
        for r, response in sorted(responses, key=lambda r: str(r[0])):
            for key, value in response.items():
                v = self.cart_session.get('contact_form_data', {}).get(key)
                v = value.bound_data(v, initial='')
                ctx['contact_info'].append((rich_text_snippet(value.label), v))

        return ctx

    @cached_property
    def confirm_messages(self):
        if self.all_optional:
            return {}
        msgs = {}
        responses = checkout_confirm_messages.send(self.request.event)
        for receiver, response in responses:
            msgs.update(response)
        return msgs

    @cached_property
    def payment_provider(self):
        if 'payment' not in self.cart_session:
            return None
        return self.request.event.get_payment_providers().get(self.cart_session['payment'])

    def get(self, request):
        self.request = request
        if 'async_id' in request.GET and settings.HAS_CELERY:
            return self.get_result(request)
        return TemplateFlowStep.get(self, request)

    @cached_property
    def all_optional(self):
        for recv, resp in checkout_all_optional.send(sender=self.request.event, request=self.request):
            if resp:
                return True
        return False

    def post(self, request):
        self.request = request

        if self.confirm_messages and not self.all_optional:
            for key, msg in self.confirm_messages.items():
                if request.POST.get('confirm_{}'.format(key)) != 'yes':
                    msg = str(_('You need to check all checkboxes on the bottom of the page.'))
                    messages.error(self.request, msg)
                    if "ajax" in self.request.POST or "ajax" in self.request.GET:
                        return JsonResponse({
                            'ready': True,
                            'redirect': self.get_error_url(),
                            'message': msg
                        })
                    return redirect(self.get_error_url())

        meta_info = {
            'contact_form_data': self.cart_session.get('contact_form_data', {}),
            'confirm_messages': [
                str(m) for m in self.confirm_messages.values()
            ]
        }
        for receiver, response in order_meta_from_request.send(sender=request.event, request=request):
            meta_info.update(response)

        return self.do(
            self.request.event.id,
            payment_provider=self.payment_provider.identifier if self.payment_provider else None,
            positions=[p.id for p in self.positions],
            email=self.cart_session.get('email'),
            locale=translation.get_language(),
            address=self.invoice_address.pk,
            meta_info=meta_info,
            sales_channel=request.sales_channel.identifier,
            gift_cards=self.cart_session.get('gift_cards'),
            shown_total=self.cart_session.get('shown_total'),
            customer=self.cart_session.get('customer'),
        )

    def get_success_message(self, value):
        create_empty_cart_id(self.request)
        return None

    def get_success_url(self, value):
        order = Order.objects.get(id=value)
        return self.get_order_url(order)

    def get_error_message(self, exception):
        if exception.__class__.__name__ == 'SendMailException':
            return _('There was an error sending the confirmation mail. Please try again later.')
        return super().get_error_message(exception)

    def get_error_url(self):
        return self.get_step_url(self.request)

    def get_order_url(self, order):
        payment = order.payments.filter(state=OrderPayment.PAYMENT_STATE_CREATED).first()
        if not payment:
            return eventreverse(self.request.event, 'presale:event.order', kwargs={
                'order': order.code,
                'secret': order.secret,
            }) + '?thanks=1'
        return eventreverse(self.request.event, 'presale:event.order.pay.complete', kwargs={
            'order': order.code,
            'secret': order.secret,
            'payment': payment.pk
        })


DEFAULT_FLOW = (
    AddOnsStep,
    CustomerStep,
    MembershipStep,
    QuestionsStep,
    PaymentStep,
    ConfirmStep
)
