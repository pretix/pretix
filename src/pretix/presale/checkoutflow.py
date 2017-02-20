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
from pretix.base.services.orders import perform_order
from pretix.base.signals import register_payment_providers
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.forms.checkout import ContactForm, InvoiceAddressForm
from pretix.presale.signals import (
    checkout_confirm_messages, checkout_flow_steps, order_meta_from_request,
)
from pretix.presale.views import CartMixin, get_cart_total
from pretix.presale.views.async import AsyncAction
from pretix.presale.views.questions import QuestionsViewMixin


class BaseCheckoutFlowStep:
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


class QuestionsStep(QuestionsViewMixin, CartMixin, TemplateFlowStep):
    priority = 50
    identifier = "questions"
    template_name = "pretixpresale/event/checkout_questions.html"

    def is_applicable(self, request):
        return True

    @cached_property
    def contact_form(self):
        return ContactForm(data=self.request.POST if self.request.method == "POST" else None,
                           initial={
                               'email': self.request.session.get('email', '')
                           })

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
        return True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['forms'] = self.forms
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
        responses = register_payment_providers.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
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
        ctx['selected'] = self.request.POST.get('payment', self.request.session.get('payment', ''))
        return ctx

    @cached_property
    def payment_provider(self):
        responses = register_payment_providers.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            if provider.identifier == self.request.session['payment']:
                return provider

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
        responses = register_payment_providers.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            if provider.identifier == self.request.session['payment']:
                return provider

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

        meta_info = {}
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
    QuestionsStep,
    PaymentStep,
    ConfirmStep
)
