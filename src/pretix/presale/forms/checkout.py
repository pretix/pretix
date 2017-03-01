from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Count, Prefetch, Q
from django.utils.formats import number_format
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import ItemVariation, Question
from pretix.base.models.orders import InvoiceAddress


class ContactForm(forms.Form):
    email = forms.EmailField(label=_('E-mail'),
                             help_text=_('Make sure to enter a valid email address. We will send you an order '
                                         'confirmation including a link that you need in case you want to make '
                                         'modifications to your order or download your ticket later.'))


class InvoiceAddressForm(forms.ModelForm):

    class Meta:
        model = InvoiceAddress
        fields = ('company', 'name', 'street', 'zipcode', 'city', 'country', 'vat_id')
        widgets = {
            'street': forms.Textarea(attrs={'rows': 2, 'placeholder': _('Street and Number')}),
        }

    def __init__(self, *args, **kwargs):
        self.event = event = kwargs.pop('event')
        super().__init__(*args, **kwargs)
        if not event.settings.invoice_address_vatid:
            del self.fields['vat_id']
        if not event.settings.invoice_address_required:
            for k, f in self.fields.items():
                f.required = False
                f.widget.is_required = False
                if 'required' in f.widget.attrs:
                    del f.widget.attrs['required']

    def clean(self):
        data = self.cleaned_data
        if not data['name'] and not data['company'] and self.event.settings.invoice_address_required:
            raise ValidationError(_('You need to provide either a company name or your name.'))


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
        cartpos = kwargs.pop('cartpos', None)
        orderpos = kwargs.pop('orderpos', None)
        item = cartpos.item if cartpos else orderpos.item
        questions = list(item.questions.all())
        event = kwargs.pop('event')

        super().__init__(*args, **kwargs)

        if item.admission and event.settings.attendee_names_asked:
            self.fields['attendee_name'] = forms.CharField(
                max_length=255, required=event.settings.attendee_names_required,
                label=_('Attendee name'),
                initial=(cartpos.attendee_name if cartpos else orderpos.attendee_name)
            )
        if item.admission and event.settings.attendee_emails_asked:
            self.fields['attendee_email'] = forms.EmailField(
                required=event.settings.attendee_emails_required,
                label=_('Attendee email'),
                initial=(cartpos.attendee_email if cartpos else orderpos.attendee_email)
            )

        for q in questions:
            # Do we already have an answer? Provide it as the initial value
            answers = [
                a for a
                in (cartpos.answers.all() if cartpos else orderpos.answers.all())
                if a.question_id == q.id
            ]
            if answers:
                initial = answers[0]
            else:
                initial = None
            if q.type == Question.TYPE_BOOLEAN:
                if q.required:
                    # For some reason, django-bootstrap3 does not set the required attribute
                    # itself.
                    widget = forms.CheckboxInput(attrs={'required': 'required'})
                else:
                    widget = forms.CheckboxInput()

                if initial:
                    initialbool = (initial.answer == "True")
                else:
                    initialbool = False

                field = forms.BooleanField(
                    label=q.question, required=q.required,
                    initial=initialbool, widget=widget
                )
            elif q.type == Question.TYPE_NUMBER:
                field = forms.DecimalField(
                    label=q.question, required=q.required,
                    initial=initial.answer if initial else None,
                    min_value=Decimal('0.00')
                )
            elif q.type == Question.TYPE_STRING:
                field = forms.CharField(
                    label=q.question, required=q.required,
                    initial=initial.answer if initial else None,
                )
            elif q.type == Question.TYPE_TEXT:
                field = forms.CharField(
                    label=q.question, required=q.required,
                    widget=forms.Textarea,
                    initial=initial.answer if initial else None,
                )
            elif q.type == Question.TYPE_CHOICE:
                field = forms.ModelChoiceField(
                    queryset=q.options.all(),
                    label=q.question, required=q.required,
                    widget=forms.RadioSelect,
                    initial=initial.options.first() if initial else None,
                )
            elif q.type == Question.TYPE_CHOICE_MULTIPLE:
                field = forms.ModelMultipleChoiceField(
                    queryset=q.options.all(),
                    label=q.question, required=q.required,
                    widget=forms.CheckboxSelectMultiple,
                    initial=initial.options.all() if initial else None,
                )
            field.question = q
            if answers:
                # Cache the answer object for later use
                field.answer = answers[0]
            self.fields['question_%s' % q.id] = field


class AddOnsForm(forms.Form):
    """
    This form class is responsible for selecting add-ons to a product in the cart.
    """

    def _label(self, event, item_or_variation):
        if isinstance(item_or_variation, ItemVariation):
            variation = item_or_variation
            item = item_or_variation.item
            price = variation.price
            price_net = variation.net_price
            label = variation.value
        else:
            item = item_or_variation
            price = item.default_price
            price_net = item.default_price_net
            label = item.name

        if not item.tax_rate or not price:
            return '{name} (+ {currency} {price})'.format(
                name=label, currency=event.currency, price=number_format(price)
            )
        elif event.settings.display_net_prices:
            return '{name} (+ {currency} {price} plus {taxes}% taxes)'.format(
                name=label, currency=event.currency, price=number_format(price_net),
                taxes=number_format(item.tax_rate)
            )
        else:
            return '{name} (+ {currency} {price} incl. {taxes}% taxes)'.format(
                name=label, currency=event.currency, price=number_format(price),
                taxes=number_format(item.tax_rate)
            )

    def __init__(self, *args, **kwargs):
        """
        Takes additional keyword arguments:

        :param category: The category to choose from
        :param event: The event this belongs to
        """
        category = kwargs.pop('category')
        event = kwargs.pop('event')
        current_addons = kwargs.pop('initial')

        super().__init__(*args, **kwargs)

        items = category.items.filter(
            Q(active=True)
            & Q(Q(available_from__isnull=True) | Q(available_from__lte=now()))
            & Q(Q(available_until__isnull=True) | Q(available_until__gte=now()))
            & Q(hide_without_voucher=False)
        ).prefetch_related(
            'variations__quotas',  # for .availability()
            Prefetch('quotas', queryset=event.quotas.all()),
            Prefetch('variations', to_attr='available_variations',
                     queryset=ItemVariation.objects.filter(active=True, quotas__isnull=False).distinct()),
        ).annotate(
            quotac=Count('quotas'),
            has_variations=Count('variations')
        ).filter(
            quotac__gt=0
        ).order_by('category__position', 'category_id', 'position', 'name')

        for i in items:
            if i.has_variations:
                field = forms.ChoiceField(
                    choices=[('', '–')] + [
                        (
                            v.pk,
                            self._label(event, v)
                        ) for v in i.available_variations
                    ],
                    label=i.name,
                    required=False,
                    widget=forms.RadioSelect,
                    initial=current_addons.get(i.pk)
                )
            else:
                field = forms.BooleanField(
                    label=self._label(event, i),
                    required=False,
                    initial=i.pk in current_addons
                )

            self.fields['item_%s' % i.pk] = field
