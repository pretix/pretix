import logging
from decimal import Decimal

import dateutil.parser
import pytz
import vat_moss.errors
import vat_moss.id
from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _

from pretix.base.forms.widgets import (
    BusinessBooleanRadio, DatePickerWidget, SplitDateTimePickerWidget,
    TimePickerWidget, UploadedFileWidget,
)
from pretix.base.models import InvoiceAddress, Question
from pretix.base.models.tax import EU_COUNTRIES
from pretix.helpers.i18n import get_format_without_seconds
from pretix.presale.signals import question_form_fields

logger = logging.getLogger(__name__)


class BaseQuestionsForm(forms.Form):
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
        cartpos = self.cartpos = kwargs.pop('cartpos', None)
        orderpos = self.orderpos = kwargs.pop('orderpos', None)
        pos = cartpos or orderpos
        item = pos.item
        questions = pos.item.questions_to_ask
        event = kwargs.pop('event')

        super().__init__(*args, **kwargs)

        if item.admission and event.settings.attendee_names_asked:
            self.fields['attendee_name'] = forms.CharField(
                max_length=255, required=event.settings.attendee_names_required,
                label=_('Attendee name'),
                initial=(cartpos.attendee_name if cartpos else orderpos.attendee_name),
            )
        if item.admission and event.settings.attendee_emails_asked:
            self.fields['attendee_email'] = forms.EmailField(
                required=event.settings.attendee_emails_required,
                label=_('Attendee email'),
                initial=(cartpos.attendee_email if cartpos else orderpos.attendee_email)
            )

        for q in questions:
            # Do we already have an answer? Provide it as the initial value
            answers = [a for a in pos.answerlist if a.question_id == q.id]
            if answers:
                initial = answers[0]
            else:
                initial = None
            tz = pytz.timezone(event.settings.timezone)
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
                    help_text=q.help_text,
                    initial=initialbool, widget=widget,
                )
            elif q.type == Question.TYPE_NUMBER:
                field = forms.DecimalField(
                    label=q.question, required=q.required,
                    help_text=q.help_text,
                    initial=initial.answer if initial else None,
                    min_value=Decimal('0.00'),
                )
            elif q.type == Question.TYPE_STRING:
                field = forms.CharField(
                    label=q.question, required=q.required,
                    help_text=q.help_text,
                    initial=initial.answer if initial else None,
                )
            elif q.type == Question.TYPE_TEXT:
                field = forms.CharField(
                    label=q.question, required=q.required,
                    help_text=q.help_text,
                    widget=forms.Textarea,
                    initial=initial.answer if initial else None,
                )
            elif q.type == Question.TYPE_CHOICE:
                field = forms.ModelChoiceField(
                    queryset=q.options,
                    label=q.question, required=q.required,
                    help_text=q.help_text,
                    widget=forms.Select,
                    empty_label='',
                    initial=initial.options.first() if initial else None,
                )
            elif q.type == Question.TYPE_CHOICE_MULTIPLE:
                field = forms.ModelMultipleChoiceField(
                    queryset=q.options,
                    label=q.question, required=q.required,
                    help_text=q.help_text,
                    widget=forms.CheckboxSelectMultiple,
                    initial=initial.options.all() if initial else None,
                )
            elif q.type == Question.TYPE_FILE:
                field = forms.FileField(
                    label=q.question, required=q.required,
                    help_text=q.help_text,
                    initial=initial.file if initial else None,
                    widget=UploadedFileWidget(position=pos, event=event, answer=initial),
                )
            elif q.type == Question.TYPE_DATE:
                field = forms.DateField(
                    label=q.question, required=q.required,
                    help_text=q.help_text,
                    initial=dateutil.parser.parse(initial.answer).date() if initial and initial.answer else None,
                    widget=DatePickerWidget(),
                )
            elif q.type == Question.TYPE_TIME:
                field = forms.TimeField(
                    label=q.question, required=q.required,
                    help_text=q.help_text,
                    initial=dateutil.parser.parse(initial.answer).time() if initial and initial.answer else None,
                    widget=TimePickerWidget(time_format=get_format_without_seconds('TIME_INPUT_FORMATS')),
                )
            elif q.type == Question.TYPE_DATETIME:
                field = forms.SplitDateTimeField(
                    label=q.question, required=q.required,
                    help_text=q.help_text,
                    initial=dateutil.parser.parse(initial.answer).astimezone(tz) if initial and initial.answer else None,
                    widget=SplitDateTimePickerWidget(time_format=get_format_without_seconds('TIME_INPUT_FORMATS')),
                )
            field.question = q
            if answers:
                # Cache the answer object for later use
                field.answer = answers[0]
            self.fields['question_%s' % q.id] = field

        responses = question_form_fields.send(sender=event, position=pos)
        data = pos.meta_info_data
        for r, response in sorted(responses, key=lambda r: str(r[0])):
            for key, value in response.items():
                # We need to be this explicit, since OrderedDict.update does not retain ordering
                self.fields[key] = value
                value.initial = data.get('question_form_data', {}).get(key)


class BaseInvoiceAddressForm(forms.ModelForm):
    vat_warning = False

    class Meta:
        model = InvoiceAddress
        fields = ('is_business', 'company', 'name', 'street', 'zipcode', 'city', 'country', 'vat_id',
                  'internal_reference')
        widgets = {
            'is_business': BusinessBooleanRadio,
            'street': forms.Textarea(attrs={'rows': 2, 'placeholder': _('Street and Number')}),
            'company': forms.TextInput(attrs={'data-display-dependency': '#id_is_business_1'}),
            'name': forms.TextInput(attrs={}),
            'vat_id': forms.TextInput(attrs={'data-display-dependency': '#id_is_business_1'}),
            'internal_reference': forms.TextInput,
        }
        labels = {
            'is_business': ''
        }

    def __init__(self, *args, **kwargs):
        self.event = event = kwargs.pop('event')
        self.request = kwargs.pop('request', None)
        self.validate_vat_id = kwargs.pop('validate_vat_id')
        super().__init__(*args, **kwargs)
        if not event.settings.invoice_address_vatid:
            del self.fields['vat_id']
        if not event.settings.invoice_address_required:
            for k, f in self.fields.items():
                f.required = False
                f.widget.is_required = False
                if 'required' in f.widget.attrs:
                    del f.widget.attrs['required']

            if event.settings.invoice_name_required:
                self.fields['name'].required = True
        else:
            self.fields['company'].widget.attrs['data-required-if'] = '#id_is_business_1'
            self.fields['name'].widget.attrs['data-required-if'] = '#id_is_business_0'

    def clean(self):
        data = self.cleaned_data
        if not data.get('name') and not data.get('company') and self.event.settings.invoice_address_required:
            raise ValidationError(_('You need to provide either a company name or your name.'))

        if 'vat_id' in self.changed_data or not data.get('vat_id'):
            self.instance.vat_id_validated = False

        if self.validate_vat_id and self.instance.vat_id_validated and 'vat_id' not in self.changed_data:
            pass
        elif self.validate_vat_id and data.get('is_business') and data.get('country') in EU_COUNTRIES and data.get('vat_id'):
            if data.get('vat_id')[:2] != str(data.get('country')):
                raise ValidationError(_('Your VAT ID does not match the selected country.'))
            try:
                result = vat_moss.id.validate(data.get('vat_id'))
                if result:
                    country_code, normalized_id, company_name = result
                    self.instance.vat_id_validated = True
                    self.instance.vat_id = normalized_id
            except vat_moss.errors.InvalidError:
                raise ValidationError(_('This VAT ID is not valid. Please re-check your input.'))
            except vat_moss.errors.WebServiceUnavailableError:
                logger.exception('VAT ID checking failed for country {}'.format(data.get('country')))
                self.instance.vat_id_validated = False
                if self.request and self.vat_warning:
                    messages.warning(self.request, _('Your VAT ID could not be checked, as the VAT checking service of '
                                                     'your country is currently not available. We will therefore '
                                                     'need to charge VAT on your invoice. You can get the tax amount '
                                                     'back via the VAT reimbursement process.'))
            except vat_moss.errors.WebServiceError:
                logger.exception('VAT ID checking failed for country {}'.format(data.get('country')))
                self.instance.vat_id_validated = False
                if self.request and self.vat_warning:
                    messages.warning(self.request, _('Your VAT ID could not be checked, as the VAT checking service of '
                                                     'your country returned an incorrect result. We will therefore '
                                                     'need to charge VAT on your invoice. Please contact support to '
                                                     'resolve this manually.'))
        else:
            self.instance.vat_id_validated = False
