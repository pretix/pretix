import copy
import json
import logging
from decimal import Decimal
from urllib.error import HTTPError

import dateutil.parser
import pycountry
import pytz
import vat_moss.errors
import vat_moss.id
from babel import localedata
from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.forms import Select
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import (
    get_language, gettext_lazy as _, pgettext_lazy,
)
from django_countries import countries
from django_countries.fields import Country, CountryField
from phonenumber_field.formfields import PhoneNumberField
from phonenumber_field.phonenumber import PhoneNumber
from phonenumber_field.widgets import PhoneNumberPrefixWidget
from phonenumbers import NumberParseException
from phonenumbers.data import _COUNTRY_CODE_TO_REGION_CODE

from pretix.base.forms.widgets import (
    BusinessBooleanRadio, DatePickerWidget, SplitDateTimePickerWidget,
    TimePickerWidget, UploadedFileWidget,
)
from pretix.base.i18n import language
from pretix.base.models import InvoiceAddress, Question, QuestionOption
from pretix.base.models.tax import EU_COUNTRIES, cc_to_vat_prefix
from pretix.base.settings import (
    COUNTRIES_WITH_STATE_IN_ADDRESS, PERSON_NAME_SCHEMES,
    PERSON_NAME_TITLE_GROUPS,
)
from pretix.base.templatetags.rich_text import rich_text
from pretix.control.forms import SplitDateTimeField
from pretix.helpers.countries import CachedCountries
from pretix.helpers.escapejson import escapejson_attr
from pretix.helpers.i18n import get_format_without_seconds
from pretix.presale.signals import question_form_fields

logger = logging.getLogger(__name__)


REQUIRED_NAME_PARTS = ['given_name', 'family_name', 'full_name']


class NamePartsWidget(forms.MultiWidget):
    widget = forms.TextInput
    autofill_map = {
        'given_name': 'given-name',
        'family_name': 'family-name',
        'middle_name': 'additional-name',
        'title': 'honorific-prefix',
        'full_name': 'name',
        'calling_name': 'nickname',
    }

    def __init__(self, scheme: dict, field: forms.Field, attrs=None, titles: list=None):
        widgets = []
        self.scheme = scheme
        self.field = field
        self.titles = titles
        for fname, label, size in self.scheme['fields']:
            a = copy.copy(attrs) or {}
            a['data-fname'] = fname
            if fname == 'title' and self.titles:
                widgets.append(Select(attrs=a, choices=[('', '')] + [(d, d) for d in self.titles[1]]))
            else:
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
                these_attrs = dict(
                    final_attrs,
                    id='%s_%s' % (id_, i),
                    title=self.scheme['fields'][i][1],
                    placeholder=self.scheme['fields'][i][1],
                )
                if self.scheme['fields'][i][0] in REQUIRED_NAME_PARTS:
                    if self.field.required:
                        these_attrs['required'] = 'required'
                    these_attrs.pop('data-no-required-attr', None)
                these_attrs['autocomplete'] = (self.attrs.get('autocomplete', '') + ' ' + self.autofill_map.get(self.scheme['fields'][i][0], 'off')).strip()
                these_attrs['data-size'] = self.scheme['fields'][i][2]
            else:
                these_attrs = final_attrs
            output.append(widget.render(name + '_%s' % i, widget_value, these_attrs, renderer=renderer))
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
        self.titles = kwargs.pop('titles')
        self.scheme = PERSON_NAME_SCHEMES.get(self.scheme_name)
        if self.titles:
            self.scheme_titles = PERSON_NAME_TITLE_GROUPS.get(self.titles)
        else:
            self.scheme_titles = None
        self.one_required = kwargs.get('required', True)
        require_all_fields = kwargs.pop('require_all_fields', False)
        kwargs['required'] = False
        kwargs['widget'] = (kwargs.get('widget') or self.widget)(
            scheme=self.scheme, titles=self.scheme_titles, field=self, **kwargs.pop('widget_kwargs', {})
        )
        defaults.update(**kwargs)
        for fname, label, size in self.scheme['fields']:
            defaults['label'] = label
            if fname == 'title' and self.scheme_titles:
                d = dict(defaults)
                d.pop('max_length', None)
                field = forms.ChoiceField(
                    **d,
                    choices=[('', '')] + [(d, d) for d in self.scheme_titles[1]]
                )
                field.part_name = fname
                fields.append(field)
            else:
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
        if self.one_required and (not value or not any(v for v in value.values())):
            raise forms.ValidationError(self.error_messages['required'], code='required')
        if self.one_required:
            for k, v in value.items():
                if k in REQUIRED_NAME_PARTS and not v:
                    raise forms.ValidationError(self.error_messages['required'], code='required')
        if self.require_all_fields and not all(v for v in value):
            raise forms.ValidationError(self.error_messages['incomplete'], code='required')
        return value


class WrappedPhoneNumberPrefixWidget(PhoneNumberPrefixWidget):
    def render(self, name, value, attrs=None, renderer=None):
        output = super().render(name, value, attrs, renderer)
        return mark_safe(self.format_output(output))

    def format_output(self, rendered_widgets) -> str:
        return '<div class="nameparts-form-group">%s</div>' % ''.join(rendered_widgets)


def guess_country(event):
    # Try to guess the initial country from either the country of the merchant
    # or the locale. This will hopefully save at least some users some scrolling :)
    locale = get_language()
    country = event.settings.invoice_address_from_country
    if not country:
        valid_countries = countries.countries
        if '-' in locale:
            parts = locale.split('-')
            if parts[1].upper() in valid_countries:
                country = Country(parts[1].upper())
            elif parts[0].upper() in valid_countries:
                country = Country(parts[0].upper())
        else:
            if locale in valid_countries:
                country = Country(locale.upper())
    return country


class QuestionCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    option_template_name = 'pretixbase/forms/widgets/checkbox_option_with_links.html'


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
        self.all_optional = kwargs.pop('all_optional', False)

        super().__init__(*args, **kwargs)

        if item.admission and event.settings.attendee_names_asked:
            self.fields['attendee_name_parts'] = NamePartsFormField(
                max_length=255,
                required=event.settings.attendee_names_required and not self.all_optional,
                scheme=event.settings.name_scheme,
                titles=event.settings.name_scheme_titles,
                label=_('Attendee name'),
                initial=(cartpos.attendee_name_parts if cartpos else orderpos.attendee_name_parts),
            )
        if item.admission and event.settings.attendee_emails_asked:
            self.fields['attendee_email'] = forms.EmailField(
                required=event.settings.attendee_emails_required and not self.all_optional,
                label=_('Attendee email'),
                initial=(cartpos.attendee_email if cartpos else orderpos.attendee_email),
                widget=forms.EmailInput(
                    attrs={
                        'autocomplete': 'email'
                    }
                )
            )
        if item.admission and event.settings.attendee_company_asked:
            self.fields['company'] = forms.CharField(
                required=event.settings.attendee_company_required and not self.all_optional,
                label=_('Company'),
                initial=(cartpos.company if cartpos else orderpos.company),
            )

        if item.admission and event.settings.attendee_addresses_asked:
            self.fields['street'] = forms.CharField(
                required=event.settings.attendee_addresses_required and not self.all_optional,
                label=_('Address'),
                widget=forms.Textarea(attrs={
                    'rows': 2,
                    'placeholder': _('Street and Number'),
                    'autocomplete': 'street-address'
                }),
                initial=(cartpos.street if cartpos else orderpos.street),
            )
            self.fields['zipcode'] = forms.CharField(
                required=event.settings.attendee_addresses_required and not self.all_optional,
                label=_('ZIP code'),
                initial=(cartpos.zipcode if cartpos else orderpos.zipcode),
                widget=forms.TextInput(attrs={
                    'autocomplete': 'postal-code',
                }),
            )
            self.fields['city'] = forms.CharField(
                required=event.settings.attendee_addresses_required and not self.all_optional,
                label=_('City'),
                initial=(cartpos.city if cartpos else orderpos.city),
                widget=forms.TextInput(attrs={
                    'autocomplete': 'address-level2',
                }),
            )
            country = (cartpos.country if cartpos else orderpos.country) or guess_country(event)
            self.fields['country'] = CountryField(
                countries=CachedCountries
            ).formfield(
                required=event.settings.attendee_addresses_required and not self.all_optional,
                label=_('Country'),
                initial=country,
                widget=forms.Select(attrs={
                    'autocomplete': 'country',
                }),
            )
            c = [('', pgettext_lazy('address', 'Select state'))]
            fprefix = str(self.prefix) + '-' if self.prefix is not None and self.prefix != '-' else ''
            cc = None
            if fprefix + 'country' in self.data:
                cc = str(self.data[fprefix + 'country'])
            elif country:
                cc = str(country)
            if cc and cc in COUNTRIES_WITH_STATE_IN_ADDRESS:
                types, form = COUNTRIES_WITH_STATE_IN_ADDRESS[cc]
                statelist = [s for s in pycountry.subdivisions.get(country_code=cc) if s.type in types]
                c += sorted([(s.code[3:], s.name) for s in statelist], key=lambda s: s[1])
            elif fprefix + 'state' in self.data:
                self.data = self.data.copy()
                del self.data[fprefix + 'state']

            self.fields['state'] = forms.ChoiceField(
                label=pgettext_lazy('address', 'State'),
                required=False,
                choices=c,
                widget=forms.Select(attrs={
                    'autocomplete': 'address-level1',
                }),
            )
            self.fields['state'].widget.is_required = True

        for q in questions:
            # Do we already have an answer? Provide it as the initial value
            answers = [a for a in pos.answerlist if a.question_id == q.id]
            if answers:
                initial = answers[0]
            else:
                initial = None
            tz = pytz.timezone(event.settings.timezone)
            help_text = rich_text(q.help_text)
            label = escape(q.question)  # django-bootstrap3 calls mark_safe
            required = q.required and not self.all_optional
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
                    label=label, required=required,
                    help_text=help_text,
                    initial=initialbool, widget=widget,
                )
            elif q.type == Question.TYPE_NUMBER:
                field = forms.DecimalField(
                    label=label, required=required,
                    help_text=q.help_text,
                    initial=initial.answer if initial else None,
                    min_value=Decimal('0.00'),
                )
            elif q.type == Question.TYPE_STRING:
                field = forms.CharField(
                    label=label, required=required,
                    help_text=help_text,
                    initial=initial.answer if initial else None,
                )
            elif q.type == Question.TYPE_TEXT:
                field = forms.CharField(
                    label=label, required=required,
                    help_text=help_text,
                    widget=forms.Textarea,
                    initial=initial.answer if initial else None,
                )
            elif q.type == Question.TYPE_COUNTRYCODE:
                field = CountryField(
                    countries=CachedCountries
                ).formfield(
                    label=label, required=required,
                    help_text=help_text,
                    widget=forms.Select,
                    empty_label='',
                    initial=initial.answer if initial else guess_country(event),
                )
            elif q.type == Question.TYPE_CHOICE:
                field = forms.ModelChoiceField(
                    queryset=q.options,
                    label=label, required=required,
                    help_text=help_text,
                    widget=forms.Select,
                    to_field_name='identifier',
                    empty_label='',
                    initial=initial.options.first() if initial else None,
                )
            elif q.type == Question.TYPE_CHOICE_MULTIPLE:
                field = forms.ModelMultipleChoiceField(
                    queryset=q.options,
                    label=label, required=required,
                    help_text=help_text,
                    to_field_name='identifier',
                    widget=QuestionCheckboxSelectMultiple,
                    initial=initial.options.all() if initial else None,
                )
            elif q.type == Question.TYPE_FILE:
                field = forms.FileField(
                    label=label, required=required,
                    help_text=help_text,
                    initial=initial.file if initial else None,
                    widget=UploadedFileWidget(position=pos, event=event, answer=initial),
                )
            elif q.type == Question.TYPE_DATE:
                field = forms.DateField(
                    label=label, required=required,
                    help_text=help_text,
                    initial=dateutil.parser.parse(initial.answer).date() if initial and initial.answer else None,
                    widget=DatePickerWidget(),
                )
            elif q.type == Question.TYPE_TIME:
                field = forms.TimeField(
                    label=label, required=required,
                    help_text=help_text,
                    initial=dateutil.parser.parse(initial.answer).time() if initial and initial.answer else None,
                    widget=TimePickerWidget(time_format=get_format_without_seconds('TIME_INPUT_FORMATS')),
                )
            elif q.type == Question.TYPE_DATETIME:
                field = SplitDateTimeField(
                    label=label, required=required,
                    help_text=help_text,
                    initial=dateutil.parser.parse(initial.answer).astimezone(tz) if initial and initial.answer else None,
                    widget=SplitDateTimePickerWidget(time_format=get_format_without_seconds('TIME_INPUT_FORMATS')),
                )
            elif q.type == Question.TYPE_PHONENUMBER:
                babel_locale = 'en'
                # Babel, and therefore django-phonenumberfield, do not support our custom locales such das de_Informal
                if localedata.exists(get_language()):
                    babel_locale = get_language()
                elif localedata.exists(get_language()[:2]):
                    babel_locale = get_language()[:2]
                with language(babel_locale):
                    default_country = guess_country(event)
                    default_prefix = None
                    for prefix, values in _COUNTRY_CODE_TO_REGION_CODE.items():
                        if str(default_country) in values:
                            default_prefix = prefix
                    try:
                        initial = PhoneNumber().from_string(initial.answer) if initial else "+{}.".format(default_prefix)
                    except NumberParseException:
                        initial = None
                    field = PhoneNumberField(
                        label=label, required=required,
                        help_text=help_text,
                        # We now exploit an implementation detail in PhoneNumberPrefixWidget to allow us to pass just
                        # a country code but no number as an initial value. It's a bit hacky, but should be stable for
                        # the future.
                        initial=initial,
                        widget=WrappedPhoneNumberPrefixWidget()
                    )
            field.question = q
            if answers:
                # Cache the answer object for later use
                field.answer = answers[0]

            if q.dependency_question_id:
                field.widget.attrs['data-question-dependency'] = q.dependency_question_id
                field.widget.attrs['data-question-dependency-values'] = escapejson_attr(json.dumps(q.dependency_values))
                if q.type != 'M':
                    field.widget.attrs['required'] = q.required and not self.all_optional
                    field._required = q.required and not self.all_optional
                field.required = False

            self.fields['question_%s' % q.id] = field

        responses = question_form_fields.send(sender=event, position=pos)
        data = pos.meta_info_data
        for r, response in sorted(responses, key=lambda r: str(r[0])):
            for key, value in response.items():
                # We need to be this explicit, since OrderedDict.update does not retain ordering
                self.fields[key] = value
                value.initial = data.get('question_form_data', {}).get(key)

        for k, v in self.fields.items():
            if v.widget.attrs.get('autocomplete') or k == 'attendee_name_parts':
                v.widget.attrs['autocomplete'] = 'section-{} '.format(self.prefix) + v.widget.attrs.get('autocomplete', '')

    def clean(self):
        d = super().clean()

        if d.get('city') and d.get('country') and str(d['country']) in COUNTRIES_WITH_STATE_IN_ADDRESS:
            if not d.get('state'):
                self.add_error('state', _('This field is required.'))

        question_cache = {f.question.pk: f.question for f in self.fields.values() if getattr(f, 'question', None)}

        def question_is_visible(parentid, qvals):
            if parentid not in question_cache:
                return False
            parentq = question_cache[parentid]
            if parentq.dependency_question_id and not question_is_visible(parentq.dependency_question_id, parentq.dependency_values):
                return False
            if 'question_%d' % parentid not in d:
                return False
            dval = d.get('question_%d' % parentid)
            return (
                ('True' in qvals and dval)
                or ('False' in qvals and not dval)
                or (isinstance(dval, QuestionOption) and dval.identifier in qvals)
                or (isinstance(dval, (list, QuerySet)) and any(qval in [o.identifier for o in dval] for qval in qvals))
            )

        def question_is_required(q):
            return (
                q.required and
                (not q.dependency_question_id or question_is_visible(q.dependency_question_id, q.dependency_values))
            )

        if not self.all_optional:
            for q in question_cache.values():
                if question_is_required(q) and not d.get('question_%d' % q.pk):
                    raise ValidationError({'question_%d' % q.pk: [_('This field is required')]})

        return d


class BaseInvoiceAddressForm(forms.ModelForm):
    vat_warning = False

    class Meta:
        model = InvoiceAddress
        fields = ('is_business', 'company', 'name_parts', 'street', 'zipcode', 'city', 'country', 'state',
                  'vat_id', 'internal_reference', 'beneficiary', 'custom_field')
        widgets = {
            'is_business': BusinessBooleanRadio,
            'street': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': _('Street and Number'),
                'autocomplete': 'street-address'
            }),
            'beneficiary': forms.Textarea(attrs={'rows': 3}),
            'country': forms.Select(attrs={
                'autocomplete': 'country',
            }),
            'zipcode': forms.TextInput(attrs={
                'autocomplete': 'postal-code',
            }),
            'city': forms.TextInput(attrs={
                'autocomplete': 'address-level2',
            }),
            'company': forms.TextInput(attrs={
                'data-display-dependency': '#id_is_business_1',
                'autocomplete': 'organization',
            }),
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
        self.all_optional = kwargs.pop('all_optional', False)

        kwargs.setdefault('initial', {})
        if not kwargs.get('instance') or not kwargs['instance'].country:
            kwargs['initial']['country'] = guess_country(self.event)

        super().__init__(*args, **kwargs)
        if not event.settings.invoice_address_vatid:
            del self.fields['vat_id']

        self.fields['country'].choices = CachedCountries()

        c = [('', pgettext_lazy('address', 'Select state'))]
        fprefix = self.prefix + '-' if self.prefix else ''
        cc = None
        if fprefix + 'country' in self.data:
            cc = str(self.data[fprefix + 'country'])
        elif 'country' in self.initial:
            cc = str(self.initial['country'])
        elif self.instance and self.instance.country:
            cc = str(self.instance.country)
        if cc and cc in COUNTRIES_WITH_STATE_IN_ADDRESS:
            types, form = COUNTRIES_WITH_STATE_IN_ADDRESS[cc]
            statelist = [s for s in pycountry.subdivisions.get(country_code=cc) if s.type in types]
            c += sorted([(s.code[3:], s.name) for s in statelist], key=lambda s: s[1])
        elif fprefix + 'state' in self.data:
            self.data = self.data.copy()
            del self.data[fprefix + 'state']

        self.fields['state'] = forms.ChoiceField(
            label=pgettext_lazy('address', 'State'),
            required=False,
            choices=c,
            widget=forms.Select(attrs={
                'autocomplete': 'address-level1',
            }),
        )
        self.fields['state'].widget.is_required = True

        if not event.settings.invoice_address_required or self.all_optional:
            for k, f in self.fields.items():
                f.required = False
                f.widget.is_required = False
                if 'required' in f.widget.attrs:
                    del f.widget.attrs['required']
        elif event.settings.invoice_address_company_required and not self.all_optional:
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
            required=event.settings.invoice_name_required and not self.all_optional,
            scheme=event.settings.name_scheme,
            titles=event.settings.name_scheme_titles,
            label=_('Name'),
            initial=(self.instance.name_parts if self.instance else self.instance.name_parts),
        )
        if event.settings.invoice_address_required and not event.settings.invoice_address_company_required and not self.all_optional:
            if not event.settings.invoice_name_required:
                self.fields['name_parts'].widget.attrs['data-required-if'] = '#id_is_business_0'
            self.fields['name_parts'].widget.attrs['data-no-required-attr'] = '1'
            self.fields['company'].widget.attrs['data-required-if'] = '#id_is_business_1'

        if not event.settings.invoice_address_beneficiary:
            del self.fields['beneficiary']

        if event.settings.invoice_address_custom_field:
            self.fields['custom_field'].label = event.settings.invoice_address_custom_field
        else:
            del self.fields['custom_field']

        for k, v in self.fields.items():
            if v.widget.attrs.get('autocomplete') or k == 'name_parts':
                v.widget.attrs['autocomplete'] = 'section-invoice billing ' + v.widget.attrs.get('autocomplete', '')

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

        if data.get('city') and data.get('country') and str(data['country']) in COUNTRIES_WITH_STATE_IN_ADDRESS:
            if not data.get('state'):
                self.add_error('state', _('This field is required.'))

        self.instance.name_parts = data.get('name_parts')

        if all(
                not v for k, v in data.items() if k not in ('is_business', 'country', 'name_parts')
        ) and len(data.get('name_parts', {})) == 1:
            # Do not save the country if it is the only field set -- we don't know the user even checked it!
            self.cleaned_data['country'] = ''

        if self.validate_vat_id and self.instance.vat_id_validated and 'vat_id' not in self.changed_data:
            pass
        elif self.validate_vat_id and data.get('is_business') and data.get('country') in EU_COUNTRIES and data.get('vat_id'):
            if data.get('vat_id')[:2] != cc_to_vat_prefix(str(data.get('country'))):
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
            except (vat_moss.errors.WebServiceError, HTTPError):
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
            if f != 'name_parts':
                del self.fields[f]
