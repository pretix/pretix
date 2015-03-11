from datetime import timedelta
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db import transaction
from django.db.models import Q, Sum
from django import forms
from django.shortcuts import redirect
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.views.generic import View, TemplateView
from django.utils.translation import ugettext_lazy as _
from pretix.base.models import CartPosition, Question, QuestionAnswer, Quota, Order, OrderPosition
from pretix.base.signals import register_payment_providers

from pretix.presale.views import EventViewMixin, CartDisplayMixin, EventLoginRequiredMixin


class QuestionsForm(forms.Form):
    """
    This form class is responsible for asking order-related questions. This includes
    the attendee name for admission tickets, if the corresponding setting is enabled,
    as well as additional questions defined by the organizer.
    """

    def __init__(self, *args, **kwargs):
        """
        Takes two additional keyword arguments:

        :param cartpos: The cart position the form should be for
        :param event: The event this belongs to
        """
        cartpos = kwargs.pop('cartpos')
        item = cartpos.item
        questions = list(item.questions.all())
        event = kwargs.pop('event')

        super().__init__(*args, **kwargs)

        if item.admission and event.settings.attendee_names_asked == 'True':
            self.fields['attendee_name'] = forms.CharField(
                max_length=255, required=(event.settings.attendee_names_required == 'True'),
                label=_('Attendee name'),
                initial=cartpos.attendee_name
            )

        for q in questions:
            # Do we already have an answer? Provide it as the initial value
            answers = [a for a in cartpos.answers.all() if a.question_id == q.identity]
            if answers:
                initial = answers[0].answer
            else:
                initial = None
            if q.type == Question.TYPE_BOOLEAN:
                field = forms.BooleanField(
                    label=q.question, required=q.required,
                    initial=initial
                )
            elif q.type == Question.TYPE_NUMBER:
                field = forms.DecimalField(
                    label=q.question, required=q.required,
                    initial=initial
                )
            elif q.type == Question.TYPE_STRING:
                field = forms.CharField(
                    label=q.question, required=q.required,
                    initial=initial
                )
            elif q.type == Question.TYPE_TEXT:
                field = forms.CharField(
                    label=q.question, required=q.required,
                    widget=forms.Textarea,
                    initial=initial
                )
            field.question = q
            if answers:
                # Cache the answer object for later use
                field.answer = answers[0]
            self.fields['question_%s' % q.identity] = field


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


class CheckoutStart(EventViewMixin, CartDisplayMixin, EventLoginRequiredMixin, CheckoutView):
    template_name = "pretixpresale/event/checkout_questions.html"

    @cached_property
    def forms(self):
        """
        A list of forms with one form for each cart cart position that has questions
        the user can answer. All forms have a custom prefix, so that they can all be
        submitted at once.
        """
        formlist = []
        for cr in self.cartpos:
            form = QuestionsForm(event=self.request.event,
                                 prefix=cr.identity,
                                 cartpos=cr,
                                 data=(self.request.POST if self.request.method == 'POST' else None))
            form.cartpos = cr
            if len(form.fields) > 0:
                formlist.append(form)
        return formlist

    def post(self, *args, **kwargs):
        failed = False
        for form in self.forms:
            # Every form represents a CartPosition with questions attached
            if not form.is_valid():
                failed = True
            else:
                # This form was correctly filled, so we store the data as
                # answers to the questions / in the CartPosition object
                for k, v in form.cleaned_data.items():
                    if k == 'attendee_name':
                        form.cartpos = form.cartpos.clone()
                        form.cartpos.attendee_name = v
                        form.cartpos.save()
                    elif k.startswith('question_'):
                        field = form.fields[k]
                        if hasattr(field, 'answer'):
                            # We already have a cached answer object, so we don't
                            # have to create a new one
                            field.answer = field.answer.clone()
                            field.answer.answer = v
                            field.answer.save()
                        else:
                            QuestionAnswer.objects.create(
                                cartposition=form.cartpos,
                                question=field.question,
                                answer=v
                            )
        if failed:
            messages.error(self.request,
                           _("We had difficulties processing your input. Please review the errors below."))
            return self.get(*args, **kwargs)
        return redirect(self.get_payment_url())

    def get(self, *args, **kwargs):
        if not self.cartpos:
            messages.error(self.request,
                           _("Your cart is empty"))
            return redirect(self.get_index_url())

        if not self.forms:
            # Nothing to do here
            return redirect(self.get_payment_url())

        return super().get(*args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['forms'] = self.forms
        return ctx


class PaymentDetails(EventViewMixin, EventLoginRequiredMixin, CheckoutView):
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
            if not provider.is_enabled:
                continue
            fee = provider.calculate_fee(self._total_order_value)
            providers.append({
                'provider': provider,
                'fee': fee,
                'form': provider.checkout_form_render(self.request),
            })
        return providers

    def post(self, request, *args, **kwargs):
        for p in self.provider_forms:
            if p['provider'].identifier == request.POST.get('payment', ''):
                request.session['payment'] = p['provider'].identifier
                total = self._total_order_value + p['provider'].calculate_fee(self._total_order_value)
                resp = p['provider'].checkout_prepare(request, total)
                if isinstance(resp, str):
                    return redirect(str)
                elif resp is True:
                    return redirect(self.get_confirm_url())
                else:
                    return self.get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['providers'] = self.provider_forms
        ctx['selected'] = self.request.POST.get('payment', self.request.session.get('payment', ''))
        return ctx


class OrderConfirm(EventViewMixin, CartDisplayMixin, EventLoginRequiredMixin, CheckoutView):
    template_name = "pretixpresale/event/checkout_confirm.html"

    error_messages = {
        'unavailable': _('Some of the items you selected were no longer available. '
                         'Please see below for details.'),
        'in_part': _('Some of the items you selected were no longer available in '
                     'the quantity you selected. Please see below for details.'),
        'price_changed': _('The price of some of the items in your cart has changed in the '
                           'meantime. Please see below for details.'),
        'busy': _('We were not able to process your request completely as the '
                  'server was too busy. Please try again.'),
        'max_items': _("You cannot select more than %s items per order"),
    }

    def __init__(self, *args, **kwargs):
        self.msg_some_unavailable = False
        super().__init__(*args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['cart'] = self.get_cart()
        ctx['payment'] = self.payment_provider.checkout_confirm_render(self.request)
        return ctx

    @cached_property
    def payment_provider(self):
        responses = register_payment_providers.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            if provider.identifier == self.request.session['payment']:
                return provider

    def check_process(self, request):
        if not self.payment_provider:
            messages.error(request, _('The payment information you entered was incomplete.'))
            return redirect(self.get_payment_url())
        if not self.payment_provider.checkout_is_valid_session(request):
            messages.error(request, _('The payment information you entered was incomplete.'))
            return redirect(self.get_payment_url())
        if len(self.cartpos) == 0:
            messages.warning(request, _('Your cart is empty.'))
            return redirect(self.get_index_url())
        for cp in self.cartpos:
            answ = {
                aw.question_id: aw.answer for aw in cp.answers.all()
            }
            for q in cp.item.questions.all():
                if q.required and q.identity not in answ:
                    messages.warning(request, _('Please fill in answers to all required questions.'))
                    return redirect(self.get_questions_url())

    def get(self, request, *args, **kwargs):
        self.request = request
        check = self.check_process(request)
        if check:
            return check
        return super().get(request, *args, **kwargs)

    def error_message(self, msg, important=False):
        if not self.msg_some_unavailable or important:
            self.msg_some_unavailable = True
            messages.error(self.request, msg)

    def post(self, request, *args, **kwargs):
        self.request = request
        check = self.check_process(request)
        if check:
            return

        dt = now()
        quotas_locked = set()

        try:
            cartpos = self.cartpos
            for i, cp in enumerate(cartpos):
                quotas = list(cp.item.quotas.all()) if cp.variation is None else list(cp.variation.quotas.all())
                if cp.expires < dt:
                    price = cp.item.check_restrictions() if cp.variation is None else cp.variation.check_restrictions()
                    if price is False:
                        self.error_message(self.error_messages['unavailable'])
                        continue
                    if len(quotas) == 0:
                        self.error_message(self.error_messages['unavailable'])
                        continue
                    if price != cp.price:
                        cp = cp.clone()
                        cartpos[i] = cp
                        cp.price = price
                        cp.save()
                        self.error_message(self.error_messages['price_changed'])
                        continue
                    quota_ok = True
                    for quota in quotas:
                        # Lock the quota, so no other thread is allowed to perform sales covered by this
                        # quota while we're doing so.
                        if quota not in quotas_locked:
                            quota.lock()
                            quotas_locked.add(quota)
                        avail = quota.availability()
                        if avail[0] != Quota.AVAILABILITY_OK:
                            # This quota is sold out/currently unavailable, so do not sell this at all
                            self.error_message(self.error_messages['unavailable'])
                            quota_ok = False
                            break
                    if quota_ok:
                        cp = cp.clone()
                        cartpos[i] = cp
                        cp.expires = now() + timedelta(minutes=self.request.event.settings.get('reservation_time', as_type=int))
                        cp.save()
            if not self.msg_some_unavailable:  # Everything went well
                with transaction.atomic():
                    total = sum([c.price for c in cartpos])
                    payment_fee = self.payment_provider.calculate_fee(total)
                    total += payment_fee
                    expires = [dt + timedelta(days=request.event.payment_term_days)]
                    if request.event.payment_term_last:
                        expires.append(request.event.payment_term_last)
                    order = Order.objects.create(
                        status=Order.STATUS_PENDING,
                        event=request.event,
                        user=request.user,
                        datetime=dt,
                        expires=min(expires),
                        total=total,
                        payment_fee=payment_fee,
                        payment_provider=self.payment_provider.identifier,
                    )
                    for cp in cartpos:
                        op = OrderPosition.objects.create(
                            order=order, item=cp.item, variation=cp.variation,
                            price=cp.price, attendee_name=cp.attendee_name
                        )
                        for answ in cp.answers.all():
                            answ = answ.clone()
                            answ.orderposition = op
                            answ.cartposition = None
                            answ.save()
                        cp.delete()
                    messages.success(request, _('Your order has been placed.'))
                resp = self.payment_provider.checkout_perform(request, order)
                if isinstance(resp, str):
                    return redirect(str)
                else:
                    return redirect(self.get_order_url(order))

        except Quota.LockTimeoutException:
            # Is raised when there are too many threads asking for quota locks and we were
            # unaible to get one
            self.error_message(self.error_messages['busy'], important=True)
        finally:
            # Release the locks. This is important ;)
            for quota in quotas_locked:
                quota.release()

        return redirect(self.get_confirm_url())
