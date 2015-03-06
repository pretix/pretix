from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db.models import Q, Sum
from django import forms
from django.shortcuts import redirect
from django.utils.functional import cached_property
from django.views.generic import View, TemplateView
from django.utils.translation import ugettext_lazy as _
from pretix.base.models import CartPosition, Question, QuestionAnswer
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


class CheckoutStart(EventViewMixin, CartDisplayMixin, EventLoginRequiredMixin, TemplateView):
    template_name = "pretixpresale/event/checkout_questions.html"

    def get_success_url(self):
        return reverse('presale:event.checkout.payment', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
        })

    def get_url(self):
        return reverse('presale:event.checkout.start', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
        })

    def get_previous_url(self):
        return reverse('presale:event.index', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
        })

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

    @cached_property
    def cartpos(self):
        """
        A list of this users cart position
        """
        return list(CartPosition.objects.current.filter(
            Q(user=self.request.user) & Q(event=self.request.event)
        ).order_by(
            'item', 'variation'
        ).select_related(
            'item', 'variation'
        ).prefetch_related(
            'variation__values', 'variation__values__prop',
            'item__questions', 'answers'
        ))

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
        return redirect(self.get_success_url())

    def get(self, *args, **kwargs):
        if not self.cartpos:
            messages.error(self.request,
                           _("Your cart is empty"))
            return redirect(self.get_previous_url())

        if not self.forms:
            # Nothing to do here
            return redirect(self.get_success_url())

        return super().get(*args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['forms'] = self.forms
        return ctx


class PaymentDetails(EventViewMixin, CartDisplayMixin, EventLoginRequiredMixin, TemplateView):
    template_name = "pretixpresale/event/checkout_payment.html"

    def get_success_url(self):
        return reverse('presale:event.index', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
        })

    def get_url(self):
        return reverse('presale:event.checkout.payment', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
        })

    def get_previous_url(self):
        return reverse('presale:event.checkout.start', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
        })

    @cached_property
    def provider_forms(self):
        total = CartPosition.objects.current.filter(
            Q(user=self.request.user) & Q(event=self.request.event)
        ).aggregate(sum=Sum('price'))['sum']
        providers = []
        responses = register_payment_providers.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            if not provider.is_enabled:
                continue
            fee = provider.calculate_fee(total)
            providers.append({
                'provider': provider,
                'fee': fee,
            })
        return providers

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['providers'] = self.provider_forms
        return ctx
