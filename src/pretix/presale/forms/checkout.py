from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Question
from pretix.base.models.orders import InvoiceAddress


class ContactForm(forms.Form):
    email = forms.EmailField(label=_('E-mail'))


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
