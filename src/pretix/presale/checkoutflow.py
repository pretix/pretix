from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import redirect
from django.utils import translation
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django.views.generic.base import TemplateResponseMixin

from pretix.base.models import Order
from pretix.base.models.orders import InvoiceAddress
from pretix.base.services.cart import set_cart_addons
from pretix.base.services.orders import perform_order
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.forms.checkout import (
    AddOnsForm, ContactForm, InvoiceAddressForm,
)
from pretix.presale.signals import (
    checkout_confirm_messages, checkout_flow_steps, contact_form_fields,
    order_meta_from_request, question_form_fields,
)
from pretix.presale.views import CartMixin, get_cart, get_cart_total
from pretix.presale.views.async import AsyncAction
from pretix.presale.views.questions import QuestionsViewMixin


class BaseCheckoutFlowStep:
    requires_valid_cart = True

    def __init__(self, event):
        self.event = event
        self.request = None

    @property
    def identifier(self):
        raise NotImplementedError()

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

    def get_step_url(self):
        return eventreverse(self.event, 'presale:event.checkout', kwargs={'step': self.identifier})

    def get_prev_url(self, request):
        prev = self.get_prev_applicable(request)
        if not prev:
            return eventreverse(self.event, 'presale:event.index')
        else:
            return prev.get_step_url()

    def get_next_url(self, request):
        n = self.get_next_applicable(request)
        if n:
            return n.get_step_url()


def get_checkout_flow(event):
    flow = list([step(event) for step in DEFAULT_FLOW])
    for receiver, response in checkout_flow_steps.send(event):
        step = response(event=event)
        if step.priority > 1000:
            raise ValueError('Plugins are not allowed to define a priority greater than 1000')
        flow.append(step)

    # Sort by priority
    flow.sort(key=lambda p: p.priority)

    # Create a double-linked-list for esasy forwards/backwards traversal
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
        kwargs.setdefault('prev_url', self.get_prev_url(self.request))
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

    def is_applicable(self, request):
        return get_cart(request).filter(item__addons__isnull=False).exists()

    def is_completed(self, request, warn=False):
        for cartpos in get_cart(request).filter(addon_to__isnull=True).prefetch_related(
            'item__addons', 'item__addons__addon_category', 'addons', 'addons__item'
        ):
            a = cartpos.addons.all()
            for iao in cartpos.item.addons.all():
                found = len([1 for p in a if p.item.category_id == iao.addon_category_id])
                if found < iao.min_count or found > iao.max_count:
                    return False
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
            'item__addons', 'item__addons__addon_category', 'addons', 'addons__variation'
        ):
            current_addon_products = {
                a.item_id: a.variation_id for a in cartpos.addons.all()
            }
            formsetentry = {
                'cartpos': cartpos,
                'item': cartpos.item,
                'variation': cartpos.variation,
                'categories': []
            }
            for iao in cartpos.item.addons.all():
                category = {
                    'category': iao.addon_category,
                    'min_count': iao.min_count,
                    'max_count': iao.max_count,
                    'form': AddOnsForm(
                        event=self.request.event,
                        prefix='{}_{}'.format(cartpos.pk, iao.addon_category.pk),
                        category=iao.addon_category,
                        initial=current_addon_products,
                        data=(self.request.POST if self.request.method == 'POST' else None),
                        quota_cache=quota_cache,
                        item_cache=item_cache
                    )
                }

                if len(category['form'].fields) > 0:
                    formsetentry['categories'].append(category)

            formset.append(formsetentry)
        return formset

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['forms'] = self.forms
        return ctx

    def get_success_message(self, value):
        return None

    def get_success_url(self, value):
        return self.get_next_url(self.request)

    def get_error_url(self):
        return self.get_step_url()

    def get(self, request):
        self.request = request
        if 'async_id' in request.GET and settings.HAS_CELERY:
            return self.get_result(request)
        return TemplateFlowStep.get(self, request)

    def post(self, request, *args, **kwargs):
        self.request = request
        is_valid = True
        data = []
        for f in self.forms:
            for c in f['categories']:
                is_valid = is_valid and c['form'].is_valid()
                if c['form'].is_valid():
                    for k, v in c['form'].cleaned_data.items():
                        itemid = int(k[5:])
                        if v is True:
                            data.append({
                                'addon_to': f['cartpos'].pk,
                                'item': itemid,
                                'variation': None
                            })
                        elif v:
                            data.append({
                                'addon_to': f['cartpos'].pk,
                                'item': itemid,
                                'variation': int(v)
                            })

        if not is_valid:
            return self.get(request, *args, **kwargs)

        return self.do(self.request.event.id, data, self.request.session.session_key)


class QuestionsStep(QuestionsViewMixin, CartMixin, TemplateFlowStep):
    priority = 50
    identifier = "questions"
    template_name = "pretixpresale/event/checkout_questions.html"

    def is_applicable(self, request):
        return True

    @cached_property
    def contact_form(self):
        initial = {
            'email': self.request.session.get('email', '')
        }
        initial.update(self.request.session.get('contact_form_data', {}))
        return ContactForm(data=self.request.POST if self.request.method == "POST" else None,
                           event=self.request.event,
                           initial=initial)

    @cached_property
    def invoice_address(self):
        iapk = self.request.session.get('invoice_address')
        if not iapk:
            return InvoiceAddress()

        try:
            return InvoiceAddress.objects.get(pk=iapk, order__isnull=True)
        except InvoiceAddress.DoesNotExist:
            return InvoiceAddress()

    @cached_property
    def invoice_form(self):
        return InvoiceAddressForm(data=self.request.POST if self.request.method == "POST" else None,
                                  event=self.request.event,
                                  instance=self.invoice_address)

    def post(self, request):
        self.request = request
        failed = not self.save() or not self.contact_form.is_valid()
        if request.event.settings.invoice_address_asked:
            failed = failed or not self.invoice_form.is_valid()
        if failed:
            messages.error(request,
                           _("We had difficulties processing your input. Please review the errors below."))
            return self.render()
        request.session['email'] = self.contact_form.cleaned_data['email']
        if request.event.settings.invoice_address_asked:
            addr = self.invoice_form.save()
            request.session['invoice_address'] = addr.pk
            request.session['contact_form_data'] = self.contact_form.cleaned_data

        return redirect(self.get_next_url(request))

    def is_completed(self, request, warn=False):
        self.request = request
        try:
            emailval = EmailValidator()
            if 'email' not in request.session:
                if warn:
                    messages.warning(request, _('Please enter a valid email address.'))
                return False
            emailval(request.session.get('email'))
        except ValidationError:
            if warn:
                messages.warning(request, _('Please enter a valid email address.'))
            return False

        for cp in self.positions:
            answ = {
                aw.question_id: aw.answer for aw in cp.answers.all()
            }
            for q in cp.item.questions.all():
                if q.required and q.id not in answ:
                    if warn:
                        messages.warning(request, _('Please fill in answers to all required questions.'))
                    return False
            if cp.item.admission and self.request.event.settings.get('attendee_names_required', as_type=bool) \
                    and cp.attendee_name is None:
                if warn:
                    messages.warning(request, _('Please fill in answers to all required questions.'))
                return False
            if cp.item.admission and self.request.event.settings.get('attendee_emails_required', as_type=bool) \
                    and cp.attendee_email is None:
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
        return ctx


class PaymentStep(QuestionsViewMixin, CartMixin, TemplateFlowStep):
    priority = 200
    identifier = "payment"
    template_name = "pretixpresale/event/checkout_payment.html"

    @cached_property
    def _total_order_value(self):
        return get_cart_total(self.request)

    @cached_property
    def provider_forms(self):
        providers = []
        for provider in self.request.event.get_payment_providers().values():
            if not provider.is_enabled or not provider.is_allowed(self.request):
                continue
            fee = provider.calculate_fee(self._total_order_value)
            providers.append({
                'provider': provider,
                'fee': fee,
                'total': self._total_order_value + fee,
                'form': provider.payment_form_render(self.request)
            })
        return providers

    def post(self, request):
        self.request = request
        for p in self.provider_forms:
            if p['provider'].identifier == request.POST.get('payment', ''):
                request.session['payment'] = p['provider'].identifier
                resp = p['provider'].checkout_prepare(
                    request, self.get_cart(payment_fee=p['provider'].calculate_fee(self._total_order_value)))
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
        ctx['selected'] = self.request.POST.get('payment', self.request.session.get('payment', ''))
        return ctx

    @cached_property
    def payment_provider(self):
        return self.request.event.get_payment_providers().get(self.request.session['payment'])

    def is_completed(self, request, warn=False):
        self.request = request
        if 'payment' not in request.session or not self.payment_provider:
            if warn:
                messages.error(request, _('The payment information you entered was incomplete.'))
            return False
        if not self.payment_provider.payment_is_valid_session(request) or \
                not self.payment_provider.is_enabled or \
                not self.payment_provider.is_allowed(request):
            if warn:
                messages.error(request, _('The payment information you entered was incomplete.'))
            return False
        return True

    def is_applicable(self, request):
        self.request = request
        if self._total_order_value == 0:
            request.session['payment'] = 'free'
            return False
        return True


class ConfirmStep(CartMixin, AsyncAction, TemplateFlowStep):
    priority = 1001
    identifier = "confirm"
    template_name = "pretixpresale/event/checkout_confirm.html"
    task = perform_order
    known_errortypes = ['OrderError']

    def is_applicable(self, request):
        return True

    def is_completed(self, request, warn=False):
        pass

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['cart'] = self.get_cart(answers=True)
        ctx['payment'] = self.payment_provider.checkout_confirm_render(self.request)
        ctx['payment_provider'] = self.payment_provider
        ctx['addr'] = self.invoice_address
        ctx['confirm_messages'] = self.confirm_messages

        ctx['contact_info'] = []
        responses = contact_form_fields.send(self.event)
        for r, response in sorted(responses, key=lambda r: str(r[0])):
            for key, value in response.items():
                v = self.request.session.get('contact_form_data', {}).get(key)
                if v is True:
                    v = _('Yes')
                elif v is False:
                    v = _('No')
                ctx['contact_info'].append((value.label, v))

        return ctx

    @cached_property
    def confirm_messages(self):
        msgs = {}
        responses = checkout_confirm_messages.send(self.request.event)
        for receiver, response in responses:
            msgs.update(response)
        return msgs

    @cached_property
    def payment_provider(self):
        return self.request.event.get_payment_providers().get(self.request.session['payment'])

    @cached_property
    def invoice_address(self):
        try:
            return InvoiceAddress.objects.get(
                pk=self.request.session.get('invoice_address'),
                order__isnull=True
            )
        except InvoiceAddress.DoesNotExist:
            return InvoiceAddress()

    def get(self, request):
        self.request = request
        if 'async_id' in request.GET and settings.HAS_CELERY:
            return self.get_result(request)
        return TemplateFlowStep.get(self, request)

    def post(self, request):
        self.request = request

        if self.confirm_messages:
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
            'contact_form_data': self.request.session.get('contact_form_data', {})
        }
        for receiver, response in order_meta_from_request.send(sender=request.event, request=request):
            meta_info.update(response)

        return self.do(self.request.event.id, self.payment_provider.identifier,
                       [p.id for p in self.positions], request.session.get('email'),
                       translation.get_language(), self.invoice_address.pk, meta_info)

    def get_success_message(self, value):
        return None

    def get_success_url(self, value):
        order = Order.objects.get(id=value)
        return self.get_order_url(order)

    def get_error_message(self, exception):
        if exception.__class__.__name__ == 'SendMailException':
            return _('There was an error sending the confirmation mail. Please try again later.')
        return super().get_error_message(exception)

    def get_error_url(self):
        return self.get_step_url()

    def get_order_url(self, order):
        return eventreverse(self.request.event, 'presale:event.order.pay.complete', kwargs={
            'order': order.code,
            'secret': order.secret
        })


DEFAULT_FLOW = (
    AddOnsStep,
    QuestionsStep,
    PaymentStep,
    ConfirmStep
)
