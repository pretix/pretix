import inspect
from collections import defaultdict
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import redirect
from django.utils import translation
from django.utils.functional import cached_property
from django.utils.translation import (
    get_language, gettext_lazy as _, pgettext_lazy,
)
from django.views.generic.base import TemplateResponseMixin
from django_scopes import scopes_disabled

from pretix.base.models import Order
from pretix.base.models.orders import InvoiceAddress, OrderPayment
from pretix.base.models.tax import TaxedPrice
from pretix.base.services.cart import (
    CartError, error_messages, get_fees, set_cart_addons, update_tax_rates,
)
from pretix.base.services.orders import perform_order
from pretix.base.signals import validate_cart_addons
from pretix.base.templatetags.rich_text import rich_text_snippet
from pretix.base.views.tasks import AsyncAction
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.forms.checkout import (
    ContactForm, InvoiceAddressForm, InvoiceNameForm,
)
from pretix.presale.signals import (
    checkout_all_optional, checkout_confirm_messages, checkout_flow_steps,
    contact_form_fields, order_meta_from_request, question_form_fields,
)
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
                                    name=a.item.tax_rule.name,
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
                                name=a.item.tax_rule.name,
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
    def contact_form(self):
        wd = self.cart_session.get('widget_data', {})
        initial = {
            'email': (
                self.cart_session.get('email', '') or
                wd.get('email', '')
            )
        }
        initial.update(self.cart_session.get('contact_form_data', {}))
        f = ContactForm(data=self.request.POST if self.request.method == "POST" else None,
                        event=self.request.event,
                        request=self.request,
                        initial=initial, all_optional=self.all_optional)
        if wd.get('email', '') and wd.get('fix', '') == "true":
            f.fields['email'].disabled = True
        return f

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
                                   validate_vat_id=self.eu_reverse_charge_relevant, all_optional=self.all_optional)
        for name, field in f.fields.items():
            if wd_initial.get(name) and wd.get('fix', '') == 'true':
                field.disabled = True
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
        self.cart_session['contact_form_data'] = self.contact_form.cleaned_data
        if self.address_asked or self.request.event.settings.invoice_name_required:
            addr = self.invoice_form.save()
            self.cart_session['invoice_address'] = addr.pk

            update_tax_rates(
                event=request.event,
                cart_id=get_or_create_cart_id(request),
                invoice_address=self.invoice_form.instance
            )

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
        return ctx


class PaymentStep(QuestionsViewMixin, CartMixin, TemplateFlowStep):
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
        for provider in self.request.event.get_payment_providers().values():
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

        self.cart_session['shown_total'] = str(ctx['cart']['total'])

        email = self.cart_session.get('contact_form_data', {}).get('email')
        if email != settings.PRETIX_EMAIL_NONE_VALUE:
            ctx['contact_info'] = [
                (_('E-mail'), email),
            ]
        else:
            ctx['contact_info'] = []
        responses = contact_form_fields.send(self.event, request=self.request)
        for r, response in sorted(responses, key=lambda r: str(r[0])):
            for key, value in response.items():
                v = self.cart_session.get('contact_form_data', {}).get(key)
                v = value.bound_data(v, initial='')
                if v is True:
                    v = _('Yes')
                elif v is False:
                    v = _('No')
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

        return self.do(self.request.event.id, self.payment_provider.identifier if self.payment_provider else None,
                       [p.id for p in self.positions], self.cart_session.get('email'),
                       translation.get_language(), self.invoice_address.pk, meta_info,
                       request.sales_channel.identifier, self.cart_session.get('gift_cards'),
                       self.cart_session.get('shown_total'))

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
    QuestionsStep,
    PaymentStep,
    ConfirmStep
)
