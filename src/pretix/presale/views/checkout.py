from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db.models import Q, Sum
from django.http import HttpRequest
from django.shortcuts import redirect
from django.utils.functional import cached_property
from django.views.generic import TemplateView
from django.utils.translation import ugettext_lazy as _
from pretix.base.models import CartPosition, QuestionAnswer, OrderPosition
from pretix.base.services.orders import perform_order, OrderError
from pretix.base.signals import register_payment_providers
from pretix.presale.forms.checkout import QuestionsForm
from pretix.presale.views import EventViewMixin, CartDisplayMixin, EventLoginRequiredMixin


class CheckoutView(TemplateView):
    def get_payment_url(self):
        return reverse('presale:event.checkout.payment', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
        })

    def get_confirm_url(self):
        return reverse('presale:event.checkout.confirm', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
        })

    def get_questions_url(self):
        return reverse('presale:event.checkout.start', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
        })

    def get_index_url(self):
        return reverse('presale:event.index', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug
        })

    def get_order_url(self, order):
        return reverse('presale:event.order', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
            'order': order.code,
        })


class QuestionsViewMixin:
    @cached_property
    def forms(self):
        """
        A list of forms with one form for each cart cart position that has questions
        the user can answer. All forms have a custom prefix, so that they can all be
        submitted at once.
        """
        formlist = []
        for cr in self.positions:
            cartpos = cr if isinstance(cr, CartPosition) else None
            orderpos = cr if isinstance(cr, OrderPosition) else None
            form = QuestionsForm(event=self.request.event,
                                 prefix=cr.identity,
                                 cartpos=cartpos,
                                 orderpos=orderpos,
                                 data=(self.request.POST if self.request.method == 'POST' else None))
            form.pos = cartpos or orderpos
            if len(form.fields) > 0:
                formlist.append(form)
        return formlist

    def save(self):
        failed = False
        for form in self.forms:
            # Every form represents a CartPosition or OrderPosition with questions attached
            if not form.is_valid():
                failed = True
            else:
                # This form was correctly filled, so we store the data as
                # answers to the questions / in the CartPosition object
                for k, v in form.cleaned_data.items():
                    if k == 'attendee_name':
                        form.pos = form.pos.clone()
                        form.pos.attendee_name = v if v != '' else None
                        form.pos.save()
                    elif k.startswith('question_') and v is not None:
                        field = form.fields[k]
                        if hasattr(field, 'answer'):
                            # We already have a cached answer object, so we don't
                            # have to create a new one
                            if v == '':
                                field.answer.delete()
                            else:
                                field.answer = field.answer.clone()
                                field.answer.answer = v
                                field.answer.save()
                        elif v != '':
                            QuestionAnswer.objects.create(
                                cartposition=(form.pos if isinstance(form.pos, CartPosition) else None),
                                orderposition=(form.pos if isinstance(form.pos, OrderPosition) else None),
                                question=field.question,
                                answer=v
                            )
        return not failed


class CheckoutStart(EventViewMixin, CartDisplayMixin, EventLoginRequiredMixin,
                    QuestionsViewMixin, CheckoutView):
    template_name = "pretixpresale/event/checkout_questions.html"

    def post(self, *args, **kwargs):
        failed = not self.save()
        if failed:
            messages.error(self.request,
                           _("We had difficulties processing your input. Please review the errors below."))
            return self.get(*args, **kwargs)
        return redirect(self.get_payment_url())

    def get(self, *args, **kwargs):
        if not self.positions:
            messages.error(self.request,
                           _("Your cart is empty"))
            return redirect(self.get_index_url())

        if not self.forms:
            # Nothing to do here
            if self.request.GET.get('back', 'false') == 'true':
                return redirect(self.get_index_url())
            return redirect(self.get_payment_url())

        return super().get(*args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['forms'] = self.forms
        return ctx


class PaymentDetails(EventViewMixin, CartDisplayMixin, EventLoginRequiredMixin, CheckoutView):
    template_name = "pretixpresale/event/checkout_payment.html"

    @cached_property
    def _total_order_value(self):
        return CartPosition.objects.current.filter(
            Q(user=self.request.user) & Q(event=self.request.event)
        ).aggregate(sum=Sum('price'))['sum']

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
                'form': provider.payment_form_render(self.request),
            })
        return providers

    def post(self, request, *args, **kwargs):
        for p in self.provider_forms:
            if p['provider'].identifier == request.POST.get('payment', ''):
                request.session['payment'] = p['provider'].identifier
                resp = p['provider'].checkout_prepare(
                    request, self.get_cart(payment_fee=p['provider'].calculate_fee(self._total_order_value)))
                if isinstance(resp, str):
                    return redirect(resp)
                elif resp is True:
                    return redirect(self.get_confirm_url())
                else:
                    return self.get(request, *args, **kwargs)
        messages.error(self.request, _("Please select a payment method."))
        return self.get(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        if self._total_order_value == 0:
            request.session['payment'] = 'free'
            return redirect(self.get_confirm_url())
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['providers'] = self.provider_forms
        ctx['selected'] = self.request.POST.get('payment', self.request.session.get('payment', ''))
        return ctx

    def get_previous_url(self):
        return self.get_questions_url() + "?back=true"


class OrderConfirm(EventViewMixin, CartDisplayMixin, EventLoginRequiredMixin, CheckoutView):
    template_name = "pretixpresale/event/checkout_confirm.html"

    def __init__(self, *args, **kwargs):
        self.msg_some_unavailable = False
        super().__init__(*args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['cart'] = self.get_cart(answers=True)
        ctx['payment'] = self.payment_provider.checkout_confirm_render(self.request)
        ctx['payment_provider'] = self.payment_provider
        return ctx

    @cached_property
    def payment_provider(self):
        responses = register_payment_providers.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            if provider.identifier == self.request.session['payment']:
                return provider

    def check_process(self, request):
        if len(self.positions) == 0:
            messages.warning(request, _('Your cart is empty.'))
            return redirect(self.get_index_url())
        if 'payment' not in request.session or not self.payment_provider:
            messages.error(request, _('The payment information you entered was incomplete.'))
            return redirect(self.get_payment_url())
        if not self.payment_provider.payment_is_valid_session(request) or \
                not self.payment_provider.is_enabled or \
                not self.payment_provider.is_allowed(request):
            messages.error(request, _('The payment information you entered was incomplete.'))
            return redirect(self.get_payment_url())
        for cp in self.positions:
            answ = {
                aw.question_id: aw.answer for aw in cp.answers.all()
            }
            for q in cp.item.questions.all():
                if q.required and q.identity not in answ:
                    messages.warning(request, _('Please fill in answers to all required questions.'))
                    return redirect(self.get_questions_url())
            if cp.item.admission and self.request.event.settings.get('attendee_names_required', as_type=bool) \
                    and cp.attendee_name is None:
                messages.warning(request, _('Please fill in answers to all required questions.'))
                return redirect(self.get_questions_url())

    def get(self, request, *args, **kwargs):
        self.request = request
        return self.check_process(request) or super().get(request, *args, **kwargs)

    def error_message(self, msg, important=False):
        if not self.msg_some_unavailable or important:
            self.msg_some_unavailable = True
            messages.error(self.request, msg)

    def post(self, request, *args, **kwargs):
        self.request = request
        return self.check_process(request) or self.perform_order(request)

    def perform_order(self, request: HttpRequest):
        try:
            order = perform_order(self.request.event, self.request.user, self.payment_provider, self.positions)
        except OrderError as e:
            messages.error(request, str(e))
            return redirect(self.get_confirm_url())
        else:
            messages.success(request, _('Your order has been placed.'))
            resp = self.payment_provider.payment_perform(request, order)
            return redirect(resp or self.get_order_url(order))

    def get_previous_url(self):
        if self.payment_provider.identifier != "free":
            return self.get_payment_url()
        else:
            return self.get_questions_url() + "?back=true"
