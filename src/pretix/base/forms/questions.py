import copy
import logging
from decimal import Decimal

import dateutil.parser
import pytz
import vat_moss.errors
import vat_moss.id
from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _

from pretix.base.forms.widgets import (
    BusinessBooleanRadio, DatePickerWidget, SplitDateTimePickerWidget,
    TimePickerWidget, UploadedFileWidget,
)
from pretix.base.models import InvoiceAddress, Question
from pretix.base.models.tax import EU_COUNTRIES
from pretix.base.settings import PERSON_NAME_SCHEMES
from pretix.control.forms import SplitDateTimeField
from pretix.helpers.i18n import get_format_without_seconds
from pretix.presale.signals import question_form_fields

logger = logging.getLogger(__name__)


class NamePartsWidget(forms.MultiWidget):
    widget = forms.TextInput

    def __init__(self, scheme: dict, field: forms.Field, attrs=None):
        widgets = []
        self.scheme = scheme
        self.field = field
        for fname, label, size in self.scheme['fields']:
            a = copy.copy(attrs) or {}
            a['data-fname'] = fname
            widgets.append(self.widget(attrs=a))
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if value is None:
            return None
        data = []
        for i, field in enumerate(self.scheme['fields']):
            fname, label, size = field
            data.append(value.get(fname, ""))
        if '_legacy' in value and not data[-1]:
            data[-1] = value.get('_legacy', '')
        return data

    def render(self, name: str, value, attrs=None, renderer=None) -> str:
        if not isinstance(value, list):
            value = self.decompress(value)
        output = []
        final_attrs = self.build_attrs(attrs or dict())
        if 'required' in final_attrs:
            del final_attrs['required']
        id_ = final_attrs.get('id', None)
        for i, widget in enumerate(self.widgets):
            try:
                widget_value = value[i]
            except (IndexError, TypeError):
                widget_value = None
            if id_:
                final_attrs = dict(
                    final_attrs,
                    id='%s_%s' % (id_, i),
                    title=self.scheme['fields'][i][1],
                    placeholder=self.scheme['fields'][i][1],
                )
                final_attrs['data-size'] = self.scheme['fields'][i][2]
            output.append(widget.render(name + '_%s' % i, widget_value, final_attrs, renderer=renderer))
        return mark_safe(self.format_output(output))

    def format_output(self, rendered_widgets) -> str:
        return '<div class="nameparts-form-group">%s</div>' % ''.join(rendered_widgets)


class NamePartsFormField(forms.MultiValueField):
    widget = NamePartsWidget

    def compress(self, data_list) -> dict:
        data = {}
        data['_scheme'] = self.scheme_name
        for i, value in enumerate(data_list):
            data[self.scheme['fields'][i][0]] = value or ''
        return data

    def __init__(self, *args, **kwargs):
        fields = []
        defaults = {
            'widget': self.widget,
            'max_length': kwargs.pop('max_length', None),
        }
        self.scheme_name = kwargs.pop('scheme')
        self.scheme = PERSON_NAME_SCHEMES.get(self.scheme_name)
        self.one_required = kwargs.get('required', True)
        require_all_fields = kwargs.pop('require_all_fields', False)
        kwargs['required'] = False
        kwargs['widget'] = (kwargs.get('widget') or self.widget)(
            scheme=self.scheme, field=self, **kwargs.pop('widget_kwargs', {})
        )
        defaults.update(**kwargs)
        for fname, label, size in self.scheme['fields']:
            defaults['label'] = label
            field = forms.CharField(**defaults)
            field.part_name = fname
            fields.append(field)
        super().__init__(
            fields=fields, require_all_fields=False, *args, **kwargs
        )
        self.require_all_fields = require_all_fields
        self.required = self.one_required

    def clean(self, value) -> dict:
        value = super().clean(value)
        if self.one_required and (not value or not any(v for v in value)):
            raise forms.ValidationError(self.error_messages['required'], code='required')
        if self.require_all_fields and not all(v for v in value):
            raise forms.ValidationError(self.error_messages['incomplete'], code='required')
        return value


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
            self.fields['attendee_name_parts'] = NamePartsFormField(
                max_length=255,
                required=event.settings.attendee_names_required,
                scheme=event.settings.name_scheme,
                label=_('Attendee name'),
                initial=(cartpos.attendee_name_parts if cartpos else orderpos.attendee_name_parts),
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
                field = SplitDateTimeField(
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
        fields = ('is_business', 'company', 'name_parts', 'street', 'zipcode', 'city', 'country', 'vat_id',
                  'internal_reference')
        widgets = {
            'is_business': BusinessBooleanRadio,
            'street': forms.Textarea(attrs={'rows': 2, 'placeholder': _('Street and Number')}),
            'company': forms.TextInput(attrs={'data-display-dependency': '#id_is_business_1'}),
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
        elif event.settings.invoice_address_company_required:
            self.initial['is_business'] = True

            self.fields['is_business'].widget = BusinessBooleanRadio(require_business=True)
            self.fields['company'].required = True
            self.fields['company'].widget.is_required = True
            self.fields['company'].widget.attrs['required'] = 'required'
            del self.fields['company'].widget.attrs['data-display-dependency']
            if 'vat_id' in self.fields:
                del self.fields['vat_id'].widget.attrs['data-display-dependency']

        self.fields['name_parts'] = NamePartsFormField(
            max_length=255,
            required=event.settings.invoice_name_required,
            scheme=event.settings.name_scheme,
            label=_('Name'),
            initial=(self.instance.name_parts if self.instance else self.instance.name_parts),
        )
        if event.settings.invoice_address_required and not event.settings.invoice_address_company_required:
            self.fields['name_parts'].widget.attrs['data-required-if'] = '#id_is_business_0'
            self.fields['name_parts'].widget.attrs['data-no-required-attr'] = '1'
            self.fields['company'].widget.attrs['data-required-if'] = '#id_is_business_1'

    def clean(self):
        data = self.cleaned_data
        if not data.get('is_business'):
            data['company'] = ''
        if self.event.settings.invoice_address_required:
            if data.get('is_business') and not data.get('company'):
                raise ValidationError(_('You need to provide a company name.'))
            if not data.get('is_business') and not data.get('name_parts'):
                raise ValidationError(_('You need to provide your name.'))

        if 'vat_id' in self.changed_data or not data.get('vat_id'):
            self.instance.vat_id_validated = False

        self.instance.name_parts = data.get('name_parts')

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
            except (vat_moss.errors.InvalidError, ValueError):
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


class BaseInvoiceNameForm(BaseInvoiceAddressForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in list(self.fields.keys()):
            if f != 'name':
                del self.fields[f]
