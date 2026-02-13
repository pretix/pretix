#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Andreas Teuber, Flavia Bastos
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import copy
import json
import logging
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from zoneinfo import ZoneInfo

import dateutil.parser
import pycountry
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.gis.geoip2 import GeoIP2
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.validators import (
    MaxValueValidator, MinValueValidator, RegexValidator,
)
from django.db.models import QuerySet
from django.forms import Select, widgets
from django.forms.widgets import FILE_INPUT_CONTRADICTION
from django.utils.formats import date_format
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.text import format_lazy
from django.utils.timezone import get_current_timezone
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_countries import countries
from django_countries.fields import Country, CountryField
from geoip2.errors import AddressNotFoundError
from phonenumber_field.formfields import PhoneNumberField
from phonenumber_field.phonenumber import PhoneNumber
from phonenumber_field.widgets import PhoneNumberPrefixWidget
from phonenumbers import (
    COUNTRY_CODE_TO_REGION_CODE, REGION_CODE_FOR_NON_GEO_ENTITY,
    NumberParseException, national_significant_number,
)
from PIL import ImageOps

from pretix.base.forms.widgets import (
    BusinessBooleanRadio, DatePickerWidget, SplitDateTimePickerWidget,
    TimePickerWidget, UploadedFileWidget,
)
from pretix.base.i18n import (
    get_babel_locale, get_language_without_region, language,
)
from pretix.base.invoicing.transmission import (
    get_transmission_types, transmission_types,
)
from pretix.base.models import InvoiceAddress, Item, Question, QuestionOption
from pretix.base.models.tax import ask_for_vat_id
from pretix.base.services.tax import (
    VATIDFinalError, VATIDTemporaryError, normalize_vat_id, validate_vat_id,
)
from pretix.base.settings import (
    COUNTRIES_WITH_STATE_IN_ADDRESS, COUNTRY_STATE_LABEL,
    PERSON_NAME_SALUTATIONS, PERSON_NAME_SCHEMES, PERSON_NAME_TITLE_GROUPS,
)
from pretix.base.templatetags.rich_text import rich_text
from pretix.base.timemachine import time_machine_now
from pretix.control.forms import (
    ExtFileField, ExtValidationMixin, SizeValidationMixin, SplitDateTimeField,
)
from pretix.helpers.countries import (
    CachedCountries, get_phone_prefixes_sorted_and_localized,
)
from pretix.helpers.escapejson import escapejson_attr
from pretix.helpers.http import get_client_ip
from pretix.helpers.i18n import get_format_without_seconds
from pretix.presale.signals import question_form_fields

logger = logging.getLogger(__name__)


REQUIRED_NAME_PARTS = ['salutation', 'given_name', 'family_name', 'full_name']


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
            elif fname == 'salutation':
                widgets.append(Select(
                    attrs=a,
                    choices=[
                        ('', '---'),
                        ('empty', '({})'.format(pgettext_lazy("name_salutation", "not specified"))),
                    ] + PERSON_NAME_SALUTATIONS
                ))
            else:
                widgets.append(self.widget(attrs=a))
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if value is None:
            return None
        data = []
        for i, field in enumerate(self.scheme['fields']):
            fname, label, size = field
            fval = value.get(fname, "")
            if fname == "salutation" and fname in value and fval == "":
                fval = "empty"
            data.append(fval)
        if '_legacy' in value and not data[-1]:
            data[-1] = value.get('_legacy', '')
        elif not any(d for d in data) and '_scheme' in value:
            scheme = PERSON_NAME_SCHEMES[value['_scheme']]
            data[-1] = scheme['concatenation'](value).strip()

        return data

    def render(self, name: str, value, attrs=None, renderer=None) -> str:
        if not isinstance(value, list):
            value = self.decompress(value)
        output = []
        final_attrs = self.build_attrs(attrs or {})
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
                )
                if not isinstance(widget, widgets.Select):
                    these_attrs['placeholder'] = self.scheme['fields'][i][1]
                if self.scheme['fields'][i][0] in REQUIRED_NAME_PARTS:
                    if self.field.required:
                        these_attrs['required'] = 'required'
                    these_attrs.pop('data-no-required-attr', None)

                autofill_section = self.attrs.get('autocomplete', '')
                autofill_by_name_scheme = self.autofill_map.get(self.scheme['fields'][i][0], 'off')
                if autofill_by_name_scheme == "off" or autofill_section.strip() == "off":
                    these_attrs['autocomplete'] = "off"
                else:
                    these_attrs['autocomplete'] = (autofill_section + ' ' + autofill_by_name_scheme).strip()
                these_attrs['data-size'] = self.scheme['fields'][i][2]
                these_attrs['aria-label'] = self.scheme['fields'][i][1]
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
            key = self.scheme['fields'][i][0]
            data[key] = value or ''
        return data

    def __init__(self, *args, **kwargs):
        fields = []
        defaults = {
            'widget': self.widget,
            'max_length': kwargs.pop('max_length', None),
            'validators': [
                RegexValidator(
                    # The following characters should never appear in a name anywhere of
                    # the world. However, they commonly appear in inputs generated by spam
                    # bots.
                    r'^[^$€/%§{}<>~]*$',
                    message=_('Please do not use special characters in names.')
                )
            ]
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
                d.pop('validators', None)
                field = forms.ChoiceField(
                    **d,
                    choices=[('', '')] + [(d, d) for d in self.scheme_titles[1]]
                )

            elif fname == 'salutation':
                d = dict(defaults)
                d.pop('max_length', None)
                d.pop('validators', None)
                field = forms.ChoiceField(
                    **d,
                    choices=[
                        ('', '---'),
                        ('empty', '({})'.format(pgettext_lazy("name_salutation", "not specified"))),
                    ] + PERSON_NAME_SALUTATIONS
                )
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
            for k, label, size in self.scheme['fields']:
                if k in REQUIRED_NAME_PARTS and not value.get(k):
                    raise forms.ValidationError(self.error_messages['required'], code='required')
        if self.require_all_fields and not all(v for v in value):
            raise forms.ValidationError(self.error_messages['incomplete'], code='required')

        if sum(len(v) for v in value.values() if v) > 250:
            raise forms.ValidationError(_('Please enter a shorter name.'), code='max_length')

        if value.get("salutation") == "empty":
            value["salutation"] = ""

        return value


def name_parts_is_empty(name_parts_dict):
    return not any(k != "_scheme" and v for k, v in name_parts_dict.items())


class WrappedPhonePrefixSelect(Select):
    initial = None

    def __init__(self, initial=None):
        choices = [("", "---------")]

        if initial:
            for prefix, values in COUNTRY_CODE_TO_REGION_CODE.items():
                if all(v == REGION_CODE_FOR_NON_GEO_ENTITY for v in values):
                    continue
                if initial in values:
                    self.initial = "+%d" % prefix
                    break
        choices += get_phone_prefixes_sorted_and_localized()
        super().__init__(choices=choices, attrs={
            'aria-label': pgettext_lazy('phonenumber', 'International area code'),
            'autocomplete': 'tel-country-code',
        })

    def render(self, name, value, *args, **kwargs):
        return super().render(name, value or self.initial, *args, **kwargs)

    def get_context(self, name, value, attrs):
        if value and self.choices[1][0] != value:
            matching_choices = len([1 for p, c in self.choices if p == value])
            if matching_choices > 1:
                # Some countries share a phone prefix, for example +1 is used all over the Americas.
                # This causes a UX problem: If the default value or the existing data is +12125552368,
                # the widget will just show the first <option> entry with value="+1" as selected,
                # which alphabetically is America Samoa, although most numbers statistically are from
                # the US. As a workaround, we detect this case and add an aditional choice value with
                # just <option value="+1">+1</option> without an explicit country.
                self.choices.insert(1, (value, value))
        context = super().get_context(name, value, attrs)
        return context


class WrappedPhoneNumberPrefixWidget(PhoneNumberPrefixWidget):

    def __init__(self, attrs=None, initial=None):
        widgets = (WrappedPhonePrefixSelect(initial), forms.TextInput(attrs={
            'aria-label': pgettext_lazy('phonenumber', 'Phone number (without international area code)'),
            'autocomplete': 'tel-national',
        }))
        super(PhoneNumberPrefixWidget, self).__init__(widgets)

    def render(self, name, value, attrs=None, renderer=None):
        output = super().render(name, value, attrs, renderer)
        return mark_safe(self.format_output(output))

    def format_output(self, rendered_widgets) -> str:
        return '<div class="nameparts-form-group">%s</div>' % ''.join(rendered_widgets)

    def decompress(self, value):
        """
        If an incomplete phone number (e.g. without country prefix) is currently entered,
        the default implementation just discards the value and shows nothing at all.
        Let's rather show something invalid, so the user is prompted to fix it, instead of
        silently deleting data.
        """
        if value:
            if isinstance(value, str):
                try:
                    value = PhoneNumber.from_string(value)
                except:
                    pass
            if isinstance(value, PhoneNumber):
                if value.country_code and value.national_number:
                    return [
                        "+%d" % value.country_code,
                        national_significant_number(value),
                    ]
                return [
                    None,
                    str(value)
                ]
            elif "." in value:
                return value.split(".")
            else:
                return [None, value]
        return [None, ""]

    def value_from_datadict(self, data, files, name):
        # In contrast to defualt implementation, do not silently fail if a number without
        # country prefix is entered
        values = super(PhoneNumberPrefixWidget, self).value_from_datadict(data, files, name)
        if values[1]:
            return "%s.%s" % tuple(values)
        return ""


def guess_country_from_request(request, event):
    if settings.HAS_GEOIP:
        g = GeoIP2()
        try:
            res = g.country(get_client_ip(request))
            if res['country_code'] and len(res['country_code']) == 2:
                return Country(res['country_code'])
        except AddressNotFoundError:
            pass
    return guess_country(event)


def guess_country(event):
    # Try to guess the initial country from either the country of the merchant
    # or the locale. This will hopefully save at least some users some scrolling :)
    country = event.settings.region or event.settings.invoice_address_from_country
    if not country:
        country = get_country_by_locale(get_language_without_region())
    return country


def get_country_by_locale(locale):
    country = None
    valid_countries = countries.countries
    if '-' in locale:
        parts = locale.split('-')
        # TODO: does this actually work?
        if parts[1].upper() in valid_countries:
            country = Country(parts[1].upper())
        elif parts[0].upper() in valid_countries:
            country = Country(parts[0].upper())
    else:
        if locale.upper() in valid_countries:
            country = Country(locale.upper())
    return country


def guess_phone_prefix(event):
    with language(get_babel_locale()):
        country = str(guess_country(event))
        return get_phone_prefix(country)


def guess_phone_prefix_from_request(request, event):
    with language(get_babel_locale()):
        country = str(guess_country_from_request(request, event))
        return get_phone_prefix(country)


def get_phone_prefix(country):
    if country == REGION_CODE_FOR_NON_GEO_ENTITY:
        return None
    for prefix, values in COUNTRY_CODE_TO_REGION_CODE.items():
        if country in values:
            return prefix
    return None


class QuestionCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    option_template_name = 'pretixbase/forms/widgets/checkbox_option_with_links.html'


class MinDateValidator(MinValueValidator):
    def __call__(self, value):
        try:
            return super().__call__(value)
        except ValidationError as e:
            e.params['limit_value'] = date_format(e.params['limit_value'], 'SHORT_DATE_FORMAT')
            raise e


class MinDateTimeValidator(MinValueValidator):
    def __call__(self, value):
        try:
            return super().__call__(value)
        except ValidationError as e:
            e.params['limit_value'] = date_format(e.params['limit_value'].astimezone(get_current_timezone()), 'SHORT_DATETIME_FORMAT')
            raise e


class MaxDateValidator(MaxValueValidator):

    def __call__(self, value):
        try:
            return super().__call__(value)
        except ValidationError as e:
            e.params['limit_value'] = date_format(e.params['limit_value'], 'SHORT_DATE_FORMAT')
            raise e


class MaxDateTimeValidator(MaxValueValidator):
    def __call__(self, value):
        try:
            return super().__call__(value)
        except ValidationError as e:
            e.params['limit_value'] = date_format(e.params['limit_value'].astimezone(get_current_timezone()), 'SHORT_DATETIME_FORMAT')
            raise e


class PortraitImageWidget(UploadedFileWidget):
    template_name = 'pretixbase/forms/widgets/portrait_image.html'

    def value_from_datadict(self, data, files, name):
        d = super().value_from_datadict(data, files, name)
        if d is not None and d is not False and d is not FILE_INPUT_CONTRADICTION:
            d._cropdata = json.loads(data.get(name + '_cropdata', '{}') or '{}')
        return d


class PortraitImageField(SizeValidationMixin, ExtValidationMixin, forms.FileField):
    widget = PortraitImageWidget
    default_error_messages = {
        'aspect_ratio_landscape': _(
            "You uploaded an image in landscape orientation. Please upload an image in portrait orientation."
        ),
        'aspect_ratio_not_3_by_4': _(
            "Please upload an image where the width is 3/4 of the height."
        ),
        'max_dimension': _(
            "The file you uploaded has a very large number of pixels, please upload an image no larger than 10000 x 10000 pixels."
        ),
        'invalid_image': _(
            "Upload a valid image. The file you uploaded was either not an "
            "image or a corrupted image."
        ),
    }

    def to_python(self, data):
        """
        Based on Django's ImageField
        """
        f = super().to_python(data)
        if f is None:
            return None

        from PIL import Image

        # We need to get a file object for Pillow. We might have a path or we might
        # have to read the data into memory.
        if hasattr(data, 'temporary_file_path'):
            file = data.temporary_file_path()
        else:
            if hasattr(data, 'read'):
                file = BytesIO(data.read())
            else:
                file = BytesIO(data['content'])

        try:
            image = Image.open(file, formats=settings.PILLOW_FORMATS_QUESTIONS_IMAGE)
            # verify() must be called immediately after the constructor.
            image.verify()

            # We want to do more than just verify(), so we need to re-open the file
            if hasattr(file, 'seek'):
                file.seek(0)
            image = Image.open(file, formats=settings.PILLOW_FORMATS_QUESTIONS_IMAGE)

            # load() is a potential DoS vector (see Django bug #18520), so we verify the size first
            if image.width > 10_000 or image.height > 10_000:
                raise ValidationError(
                    self.error_messages['max_dimension'],
                    code='max_dimension',
                )

            image.load()

            # Annotating so subclasses can reuse it for their own validation
            f.image = image
            # Pillow doesn't detect the MIME type of all formats. In those
            # cases, content_type will be None.
            f.content_type = Image.MIME.get(image.format)

            # before we calc aspect ratio, we need to check and apply EXIF-orientation
            image = ImageOps.exif_transpose(image)

            if f._cropdata:
                image = image.crop((
                    f._cropdata.get('x', 0),
                    f._cropdata.get('y', 0),
                    f._cropdata.get('x', 0) + f._cropdata.get('width', image.width),
                    f._cropdata.get('y', 0) + f._cropdata.get('height', image.height),
                ))
                with BytesIO() as output:
                    # This might use a lot of memory, but temporary files are not a good option since
                    # we don't control the cleanup
                    image.save(output, format=f.image.format)
                    f = SimpleUploadedFile(f.name, output.getvalue(), f.content_type)
                    f.image = image

            if image.width > image.height:
                raise ValidationError(
                    self.error_messages['aspect_ratio_landscape'],
                    code='aspect_ratio_landscape',
                )

            if not 3 / 4 * .95 < image.width / image.height < 3 / 4 * 1.05:  # give it some tolerance
                raise ValidationError(
                    self.error_messages['aspect_ratio_not_3_by_4'],
                    code='aspect_ratio_not_3_by_4',
                )
        except Exception as exc:
            logger.exception('Could not parse image')
            # Pillow doesn't recognize it as an image.
            if isinstance(exc, ValidationError):
                raise
            raise ValidationError(
                self.error_messages['invalid_image'],
                code='invalid_image',
            ) from exc
        if hasattr(f, 'seek') and callable(f.seek):
            f.seek(0)
        return f

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('ext_whitelist', settings.FILE_UPLOAD_EXTENSIONS_QUESTION_IMAGE)
        kwargs.setdefault('max_size', settings.FILE_UPLOAD_MAX_SIZE_IMAGE)
        super().__init__(*args, **kwargs)


class BaseQuestionsForm(forms.Form):
    """
    This form class is responsible for asking order-related questions. This includes
    the attendee name for admission tickets, if the corresponding setting is enabled,
    as well as additional questions defined by the organizer.
    """
    address_validation = False

    def __init__(self, *args, **kwargs):
        """
        Takes two additional keyword arguments:

        :param cartpos: The cart position the form should be for
        :param event: The event this belongs to
        """
        request = kwargs.pop('request', None)
        cartpos = self.cartpos = kwargs.pop('cartpos', None)
        orderpos = self.orderpos = kwargs.pop('orderpos', None)
        pos = cartpos or orderpos
        item = pos.item
        questions = pos.item.questions_to_ask
        event = kwargs.pop('event')
        self.all_optional = kwargs.pop('all_optional', False)
        self.attendee_addresses_required = event.settings.attendee_addresses_required and not self.all_optional

        super().__init__(*args, **kwargs)

        if cartpos and item.validity_mode == Item.VALIDITY_MODE_DYNAMIC and item.validity_dynamic_start_choice:
            if item.validity_dynamic_start_choice_day_limit:
                max_date = time_machine_now().astimezone(event.timezone) + timedelta(days=item.validity_dynamic_start_choice_day_limit)
            else:
                max_date = None
            min_date = time_machine_now()
            initial = None
            if (item.require_membership or (pos.variation and pos.variation.require_membership)) and pos.used_membership:
                if pos.used_membership.date_start >= time_machine_now():
                    initial = min_date = pos.used_membership.date_start
                max_date = min(max_date, pos.used_membership.date_end) if max_date else pos.used_membership.date_end
            if item.validity_dynamic_duration_months or item.validity_dynamic_duration_days:
                attrs = {}
                if max_date:
                    attrs['data-max'] = max_date.date().isoformat()
                if min_date:
                    attrs['data-min'] = min_date.date().isoformat()
                self.fields['requested_valid_from'] = forms.DateField(
                    label=_('Start date'),
                    help_text='' if initial else _('If you keep this empty, the ticket will be valid starting at the time of purchase.'),
                    required=bool(initial),
                    initial=pos.requested_valid_from or initial,
                    widget=DatePickerWidget(attrs),
                    validators=([MaxDateValidator(max_date.date())] if max_date else []) + [MinDateValidator(min_date.date())]
                )
            else:
                self.fields['requested_valid_from'] = forms.SplitDateTimeField(
                    label=_('Start date'),
                    help_text='' if initial else _('If you keep this empty, the ticket will be valid starting at the time of purchase.'),
                    required=bool(initial),
                    initial=pos.requested_valid_from or initial,
                    widget=SplitDateTimePickerWidget(
                        time_format=get_format_without_seconds('TIME_INPUT_FORMATS'),
                        min_date=min_date,
                        max_date=max_date
                    ),
                    validators=([MaxDateTimeValidator(max_date)] if max_date else []) + [MinDateTimeValidator(min_date)]
                )

        add_fields = {}

        if item.ask_attendee_data and event.settings.attendee_names_asked:
            add_fields['attendee_name_parts'] = NamePartsFormField(
                max_length=255,
                required=event.settings.attendee_names_required and not self.all_optional,
                scheme=event.settings.name_scheme,
                titles=event.settings.name_scheme_titles,
                label=_('Attendee name'),
                initial=(cartpos.attendee_name_parts if cartpos else orderpos.attendee_name_parts),
            )
        if item.ask_attendee_data and event.settings.attendee_emails_asked:
            add_fields['attendee_email'] = forms.EmailField(
                required=event.settings.attendee_emails_required and not self.all_optional,
                label=_('Attendee email'),
                initial=(cartpos.attendee_email if cartpos else orderpos.attendee_email),
                widget=forms.EmailInput(
                    attrs={
                        'autocomplete': 'email'
                    }
                )
            )
        if item.ask_attendee_data and event.settings.attendee_company_asked:
            add_fields['company'] = forms.CharField(
                required=event.settings.attendee_company_required and not self.all_optional,
                label=_('Company'),
                max_length=255,
                initial=(cartpos.company if cartpos else orderpos.company),
            )

        if item.ask_attendee_data and event.settings.attendee_addresses_asked:
            add_fields['street'] = forms.CharField(
                required=self.attendee_addresses_required,
                label=_('Address'),
                widget=forms.Textarea(attrs={
                    'rows': 2,
                    'placeholder': _('Street and Number'),
                    'autocomplete': 'street-address'
                }),
                initial=(cartpos.street if cartpos else orderpos.street),
            )
            add_fields['zipcode'] = forms.CharField(
                required=False,
                max_length=30,
                label=_('ZIP code'),
                initial=(cartpos.zipcode if cartpos else orderpos.zipcode),
                widget=forms.TextInput(attrs={
                    'autocomplete': 'postal-code',
                }),
            )
            add_fields['city'] = forms.CharField(
                required=False,
                label=_('City'),
                max_length=255,
                initial=(cartpos.city if cartpos else orderpos.city),
                widget=forms.TextInput(attrs={
                    'autocomplete': 'address-level2',
                }),
            )
            country = (cartpos.country if cartpos else orderpos.country) or guess_country_from_request(request, event)
            add_fields['country'] = CountryField(
                countries=CachedCountries
            ).formfield(
                required=self.attendee_addresses_required,
                label=_('Country'),
                initial=country,
                widget=forms.Select(attrs={
                    'autocomplete': 'country',
                    'data-trigger-address-info': 'on',
                }),
            )
            c = [('', '---')]
            fprefix = str(self.prefix) + '-' if self.prefix is not None and self.prefix != '-' else ''
            cc = None
            state = None
            if fprefix + 'country' in self.data:
                cc = str(self.data[fprefix + 'country'])
            elif country:
                cc = str(country)
            if cc and cc in COUNTRIES_WITH_STATE_IN_ADDRESS:
                types, form = COUNTRIES_WITH_STATE_IN_ADDRESS[cc]
                statelist = [s for s in pycountry.subdivisions.get(country_code=cc) if s.type in types]
                c += sorted([(s.code[3:], s.name) for s in statelist], key=lambda s: s[1])
                state = (cartpos.state if cartpos else orderpos.state)
            elif fprefix + 'state' in self.data:
                self.data = self.data.copy()
                del self.data[fprefix + 'state']

            add_fields['state'] = forms.ChoiceField(
                label=pgettext_lazy('address', 'State'),
                required=False,
                choices=c,
                initial=state,
                widget=forms.Select(attrs={
                    'autocomplete': 'address-level1',
                }),
            )
            add_fields['state'].widget.is_required = True

        field_positions = list(
            [
                (n, event.settings.system_question_order.get(n if n != 'state' else 'country', 0))
                for n in add_fields.keys()
            ]
        )

        for q in questions:
            # Do we already have an answer? Provide it as the initial value
            answers = [a for a in pos.answerlist if a.question_id == q.id]
            if answers:
                initial = answers[0]
            else:
                initial = None
            tz = ZoneInfo(event.settings.timezone)
            help_text = rich_text(q.help_text)
            label = escape(q.question)  # django-bootstrap3 calls mark_safe
            required = q.required and not self.all_optional
            if q.type == Question.TYPE_BOOLEAN:
                if required:
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
                    min_value=q.valid_number_min or Decimal('0.00'),
                    max_value=q.valid_number_max,
                    help_text=help_text,
                    initial=initial.answer if initial else None,
                )
            elif q.type == Question.TYPE_STRING:
                field = forms.CharField(
                    label=label, required=required,
                    max_length=q.valid_string_length_max,
                    help_text=help_text,
                    initial=initial.answer if initial else None,
                )
            elif q.type == Question.TYPE_TEXT:
                field = forms.CharField(
                    label=label, required=required,
                    max_length=q.valid_string_length_max,
                    help_text=help_text,
                    widget=forms.Textarea,
                    initial=initial.answer if initial else None,
                )
            elif q.type == Question.TYPE_COUNTRYCODE:
                field = CountryField(
                    countries=CachedCountries,
                    blank=True, null=True, blank_label=' ',
                ).formfield(
                    label=label, required=required,
                    help_text=help_text,
                    widget=forms.Select,
                    empty_label=' ',
                    initial=initial.answer if initial else (guess_country_from_request(request, event) if required else None),
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
                if q.valid_file_portrait:
                    field = PortraitImageField(
                        label=label, required=required,
                        help_text=help_text,
                        initial=initial.file if initial else None,
                        widget=PortraitImageWidget(position=pos, event=event, answer=initial, attrs={'data-portrait-photo': 'true'}),
                    )
                else:
                    field = ExtFileField(
                        label=label, required=required,
                        help_text=help_text,
                        initial=initial.file if initial else None,
                        widget=UploadedFileWidget(position=pos, event=event, answer=initial),
                        ext_whitelist=settings.FILE_UPLOAD_EXTENSIONS_OTHER,
                        max_size=settings.FILE_UPLOAD_MAX_SIZE_OTHER,
                    )
            elif q.type == Question.TYPE_DATE:
                attrs = {}
                if q.valid_date_min:
                    attrs['data-min'] = q.valid_date_min.isoformat()
                if q.valid_date_max:
                    attrs['data-max'] = q.valid_date_max.isoformat()
                if not help_text:
                    if q.valid_date_min and q.valid_date_max:
                        help_text = format_lazy(
                            _('Please enter a date between {min} and {max}.'),
                            min=date_format(q.valid_date_min, "SHORT_DATE_FORMAT"),
                            max=date_format(q.valid_date_max, "SHORT_DATE_FORMAT"),
                        )
                    elif q.valid_date_min:
                        help_text = format_lazy(
                            _('Please enter a date no earlier than {min}.'),
                            min=date_format(q.valid_date_min, "SHORT_DATE_FORMAT"),
                        )
                    elif q.valid_date_max:
                        help_text = format_lazy(
                            _('Please enter a date no later than {max}.'),
                            max=date_format(q.valid_date_max, "SHORT_DATE_FORMAT"),
                        )
                if initial and initial.answer:
                    try:
                        _initial = dateutil.parser.parse(initial.answer).date()
                    except dateutil.parser.ParserError:
                        _initial = None
                else:
                    _initial = None
                field = forms.DateField(
                    label=label, required=required,
                    help_text=help_text,
                    initial=_initial,
                    widget=DatePickerWidget(attrs),
                )
                if q.valid_date_min:
                    field.validators.append(MinDateValidator(q.valid_date_min))
                if q.valid_date_max:
                    field.validators.append(MaxDateValidator(q.valid_date_max))
            elif q.type == Question.TYPE_TIME:
                if initial and initial.answer:
                    try:
                        _initial = dateutil.parser.parse(initial.answer).time()
                    except dateutil.parser.ParserError:
                        _initial = None
                else:
                    _initial = None
                field = forms.TimeField(
                    label=label, required=required,
                    help_text=help_text,
                    initial=_initial,
                    widget=TimePickerWidget(time_format=get_format_without_seconds('TIME_INPUT_FORMATS')),
                )
            elif q.type == Question.TYPE_DATETIME:
                if not help_text:
                    if q.valid_datetime_min and q.valid_datetime_max:
                        help_text = format_lazy(
                            _('Please enter a date and time between {min} and {max}.'),
                            min=date_format(q.valid_datetime_min, "SHORT_DATETIME_FORMAT"),
                            max=date_format(q.valid_datetime_max, "SHORT_DATETIME_FORMAT"),
                        )
                    elif q.valid_datetime_min:
                        help_text = format_lazy(
                            _('Please enter a date and time no earlier than {min}.'),
                            min=date_format(q.valid_datetime_min, "SHORT_DATETIME_FORMAT"),
                        )
                    elif q.valid_datetime_max:
                        help_text = format_lazy(
                            _('Please enter a date and time no later than {max}.'),
                            max=date_format(q.valid_datetime_max, "SHORT_DATETIME_FORMAT"),
                        )

                if initial and initial.answer:
                    try:
                        _initial = dateutil.parser.parse(initial.answer).astimezone(tz)
                    except dateutil.parser.ParserError:
                        _initial = None
                else:
                    _initial = None

                field = SplitDateTimeField(
                    label=label, required=required,
                    help_text=help_text,
                    initial=_initial,
                    widget=SplitDateTimePickerWidget(
                        time_format=get_format_without_seconds('TIME_INPUT_FORMATS'),
                        min_date=q.valid_datetime_min,
                        max_date=q.valid_datetime_max
                    ),
                )
                if q.valid_datetime_min:
                    field.validators.append(MinDateTimeValidator(q.valid_datetime_min))
                if q.valid_datetime_max:
                    field.validators.append(MaxDateTimeValidator(q.valid_datetime_max))
            elif q.type == Question.TYPE_PHONENUMBER:
                if initial:
                    try:
                        initial = PhoneNumber().from_string(initial.answer)
                    except NumberParseException:
                        initial = None

                if not initial:
                    phone_prefix = guess_phone_prefix_from_request(request, event)
                    if phone_prefix:
                        initial = "+{}.".format(phone_prefix)

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

            add_fields['question_%s' % q.id] = field
            field_positions.append(('question_%s' % q.id, q.position))

        field_positions.sort(key=lambda e: e[1])
        for fname, p in field_positions:
            self.fields[fname] = add_fields[fname]

        responses = question_form_fields.send(sender=event, position=pos)
        data = pos.meta_info_data
        for r, response in sorted(responses, key=lambda r: str(r[0])):
            for key, value in response.items():
                # We need to be this explicit, since OrderedDict.update does not retain ordering
                self.fields[key] = value
                value.initial = data.get('question_form_data', {}).get(key)

        for k, v in self.fields.items():
            if isinstance(v.widget, forms.MultiWidget):
                for w in v.widget.widgets:
                    autocomplete = w.attrs.get('autocomplete', '')
                    if autocomplete.strip() == "off":
                        w.attrs['autocomplete'] = 'off'
                    else:
                        w.attrs['autocomplete'] = 'section-{} '.format(self.prefix) + autocomplete
            if v.widget.attrs.get('autocomplete') or k == 'attendee_name_parts':
                autocomplete = v.widget.attrs.get('autocomplete', '')
                if autocomplete.strip() == "off":
                    v.widget.attrs['autocomplete'] = 'off'
                else:
                    v.widget.attrs['autocomplete'] = 'section-{} '.format(self.prefix) + autocomplete

    def clean(self):
        from pretix.base.addressvalidation import \
            validate_address  # local import to prevent impact on startup time

        d = super().clean()

        if self.address_validation:
            self.cleaned_data = d = validate_address(d, all_optional=not self.attendee_addresses_required)

        if d.get('street') and d.get('country') and str(d['country']) in COUNTRIES_WITH_STATE_IN_ADDRESS:
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
                answer = d.get('question_%d' % q.pk)
                field = self['question_%d' % q.pk]
                if question_is_required(q) and not answer and answer != 0 and not field.errors:
                    raise ValidationError({'question_%d' % q.pk: [_('This field is required.')]})

        # Strip invisible question from cleaned_data so they don't end up in the database
        for q in question_cache.values():
            answer = d.get('question_%d' % q.pk)
            if q.dependency_question_id and not question_is_visible(q.dependency_question_id, q.dependency_values) and answer is not None:
                d['question_%d' % q.pk] = None

        return d


class BaseInvoiceAddressForm(forms.ModelForm):
    vat_warning = False
    address_validation = False

    class Meta:
        model = InvoiceAddress
        fields = ('is_business', 'company', 'name_parts', 'street', 'zipcode', 'city', 'country', 'state',
                  'vat_id', 'internal_reference', 'beneficiary', 'custom_field')
        widgets = {
            'is_business': BusinessBooleanRadio,
            'street': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': _('Street and Number'),
                'autocomplete': 'street-address',
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
                'autocomplete': 'organization',
            }),
            'vat_id': forms.TextInput(),
            'internal_reference': forms.TextInput,
        }
        labels = {
            'is_business': ''
        }

    @property
    def ask_vat_id(self):
        return self.event.settings.invoice_address_vatid

    @property
    def address_required(self):
        return self.event.settings.invoice_address_required

    @property
    def company_required(self):
        return self.event.settings.invoice_address_company_required

    def __init__(self, *args, **kwargs):
        self.event = event = kwargs.pop('event')
        self.request = kwargs.pop('request', None)
        self.validate_vat_id = kwargs.pop('validate_vat_id')
        self.all_optional = kwargs.pop('all_optional', False)

        kwargs.setdefault('initial', {})
        if (not kwargs.get('instance') or not kwargs['instance'].country) and not kwargs["initial"].get("country"):
            kwargs['initial']['country'] = guess_country_from_request(self.request, self.event)

        if kwargs.get('instance') and kwargs['instance'].transmission_type:
            ttype, meta = transmission_types.get(identifier=kwargs['instance'].transmission_type)
            if ttype:
                kwargs['initial'].update(ttype.transmission_info_to_form_data(kwargs['instance'].transmission_info or {}))
                kwargs['initial']['transmission_type'] = ttype.identifier

        super().__init__(*args, **kwargs)

        # Individuals do not have a company name or VAT ID
        self.fields["company"].widget.attrs["data-display-dependency"] = f'input[name="{self.add_prefix("is_business")}"][value="business"]'
        self.fields["vat_id"].widget.attrs["data-display-dependency"] = f'input[name="{self.add_prefix("is_business")}"][value="business"]'

        # The internal reference is a very business-specific field and might confuse non-business users
        self.fields["internal_reference"].widget.attrs["data-display-dependency"] = f'input[name="{self.add_prefix("is_business")}"][value="business"]'

        if not self.ask_vat_id:
            del self.fields['vat_id']
        elif self.validate_vat_id:
            self.fields['vat_id'].help_text = '<br/>'.join([
                str(_('Optional, but depending on the country you reside in we might need to charge you '
                      'additional taxes if you do not enter it.')),
            ])
        else:
            self.fields['vat_id'].help_text = '<br/>'.join([
                str(_('Optional, but it might be required for you to claim tax benefits on your invoice '
                      'depending on your and the seller’s country of residence.')),
            ])

        transmission_type_choices = [
            (t.identifier, t.public_name) for t in get_transmission_types()
        ]
        if not self.address_required or self.all_optional:
            transmission_type_choices.insert(0, ("-", _("No invoice requested")))
        self.fields['transmission_type'] = forms.ChoiceField(
            label=_('Invoice transmission method'),
            choices=transmission_type_choices
        )

        self.fields['country'].choices = CachedCountries()

        c = [('', '---')]
        fprefix = self.prefix + '-' if self.prefix else ''
        cc = None
        if fprefix + 'country' in self.data:
            cc = str(self.data[fprefix + 'country'])
        elif 'country' in self.initial:
            cc = str(self.initial['country'])
        elif self.instance and self.instance.country:
            cc = str(self.instance.country)
        state_label = pgettext_lazy('address', 'State')
        if cc and cc in COUNTRIES_WITH_STATE_IN_ADDRESS:
            types, form = COUNTRIES_WITH_STATE_IN_ADDRESS[cc]
            statelist = [s for s in pycountry.subdivisions.get(country_code=cc) if s.type in types]
            c += sorted([(s.code[3:], s.name) for s in statelist], key=lambda s: s[1])
            if cc in COUNTRY_STATE_LABEL:
                state_label = COUNTRY_STATE_LABEL[cc]
        elif fprefix + 'state' in self.data:
            self.data = self.data.copy()
            del self.data[fprefix + 'state']

        self.fields['state'] = forms.ChoiceField(
            label=state_label,
            required=False,
            choices=c,
            widget=forms.Select(attrs={
                'autocomplete': 'address-level1',
            }),
        )
        self.fields['state'].widget.is_required = True

        self.fields['street'].required = False
        self.fields['zipcode'].required = False
        self.fields['city'].required = False

        # Without JavaScript the VAT ID field is not hidden, so we empty the field if a country outside the EU is selected.
        if cc and not ask_for_vat_id(cc) and fprefix + 'vat_id' in self.data:
            self.data = self.data.copy()
            del self.data[fprefix + 'vat_id']

        if not self.address_required or self.all_optional:
            for k, f in self.fields.items():
                f.required = False
                f.widget.is_required = False
                if 'required' in f.widget.attrs:
                    del f.widget.attrs['required']
        elif self.company_required and not self.all_optional:
            self.initial['is_business'] = True

            self.fields['is_business'].widget = BusinessBooleanRadio(require_business=True)
            self.fields['company'].required = True
            self.fields['company'].widget.is_required = True
            self.fields['company'].widget.attrs['required'] = 'required'
            del self.fields['company'].widget.attrs['data-display-dependency']

        self.fields['name_parts'] = NamePartsFormField(
            max_length=255,
            required=event.settings.invoice_name_required and not self.all_optional,
            scheme=event.settings.name_scheme,
            titles=event.settings.name_scheme_titles,
            label=_('Name'),
            initial=self.instance.name_parts,
        )
        if self.address_required and not self.company_required and not self.all_optional:
            if not event.settings.invoice_name_required:
                self.fields['name_parts'].widget.attrs['data-required-if'] = f'input[name="{self.add_prefix("is_business")}"][value="individual"]'
            self.fields['name_parts'].widget.attrs['data-no-required-attr'] = '1'
            self.fields['company'].widget.attrs['data-required-if'] = f'input[name="{self.add_prefix("is_business")}"][value="business"]'

        if not event.settings.invoice_address_beneficiary:
            del self.fields['beneficiary']

        if event.settings.invoice_address_custom_field:
            self.fields['custom_field'].label = event.settings.invoice_address_custom_field
            self.fields['custom_field'].help_text = event.settings.invoice_address_custom_field_helptext
        else:
            del self.fields['custom_field']

        # Add transmission type specific fields
        for transmission_type in get_transmission_types():
            for k, f in transmission_type.invoice_address_form_fields.items():
                if (
                    transmission_type.identifier == "email" and
                    k in ("transmission_email_other", "transmission_email_address") and
                    (
                        event.settings.invoice_generate == "False" or
                        not event.settings.invoice_email_attachment
                    )
                ):
                    # This looks like a very unclean hack (and probably really is one), but hear me out:
                    # With pretix 2025.7, we introduced invoice transmission types and added the "send to another email"
                    # feature for the email provider. This feature was previously part of the bank transfer payment
                    # provider and opt-in. With this change, this feature becomes available for all pretix shops, which
                    # we think is a good thing in the long run as it is an useful feature for every business customer.
                    # However, there's two scenarios where it might be bad that we add it without opt-in:
                    # - When the organizer has turned off invoice generation in pretix and is collecting invoice information
                    #   only for other reasons or to later create invoices with a separate software. In this case it
                    #   would be very bad for the user to be able to ask for the invoice to be sent somewhere else, and
                    #   that information then be ignored because the organizer has not updated their process.
                    # - When the organizer has intentionally turned off invoices being attached to emails, because that
                    #   would somehow be a contradiction.
                    # Now, the obvious solution would be to make the TransmissionType.invoice_address_form_fields property
                    # a function that depends on the event as an input. However, I believe this is the wrong approach
                    # over the long term. As a generalized concept, we DO want invoice address collection to be
                    # *independent* of event settings, in order to (later) e.g. implement invoice address editing within
                    # customer accounts. Hence, this hack directly in the form to provide (some) backwards compatibility
                    # only for the default transmission type "email".
                    continue

                self.fields[k] = f
                f._required = f.required
                f.required = False
                f.widget.is_required = False
                if 'required' in f.widget.attrs:
                    del f.widget.attrs['required']

        for k, v in self.fields.items():
            if v.widget.attrs.get('autocomplete') or k == 'name_parts':
                autocomplete = v.widget.attrs.get('autocomplete', '')
                if autocomplete.strip() == "off":
                    v.widget.attrs['autocomplete'] = 'off'
                else:
                    v.widget.attrs['autocomplete'] = 'section-invoice billing ' + autocomplete

        self.fields['country'].widget.attrs['data-trigger-address-info'] = 'on'
        self.fields['is_business'].widget.attrs['data-trigger-address-info'] = 'on'
        self.fields['transmission_type'].widget.attrs['data-trigger-address-info'] = 'on'

    def clean(self):
        from pretix.base.addressvalidation import \
            validate_address  # local import to prevent impact on startup time

        data = self.cleaned_data

        if not data.get('is_business'):
            data['company'] = ''
            data['vat_id'] = ''
        if data.get('is_business') and not ask_for_vat_id(data.get('country')):
            data['vat_id'] = ''
        if self.address_validation and self.address_required and not self.all_optional:
            if data.get('is_business') and not data.get('company'):
                raise ValidationError({"company": _('You need to provide a company name.')})
            if not data.get('is_business') and name_parts_is_empty(data.get('name_parts', {})):
                raise ValidationError(_('You need to provide your name.'))
            if not data.get('street') and not data.get('zipcode') and not data.get('city'):
                raise ValidationError({"street": _('This field is required.')})

        if 'vat_id' in self.changed_data or not data.get('vat_id'):
            self.instance.vat_id_validated = False

        if self.address_validation:
            self.cleaned_data = data = validate_address(data, self.all_optional)

        self.instance.name_parts = data.get('name_parts')

        form_is_empty = all(
            not v for k, v in data.items()
            if k not in ('is_business', 'country', 'name_parts', 'transmission_type') and not k.startswith("transmission_")
        ) and name_parts_is_empty(data.get('name_parts', {}))

        if form_is_empty:
            # Do not save the country if it is the only field set -- we don't know the user even checked it!
            self.cleaned_data['country'] = ''
            if data.get('transmission_type') == "-":
                data['transmission_type'] = 'email'  # our actual default for now, we can revisit this later

        else:
            if data.get('transmission_type') == "-":
                raise ValidationError(
                    {"transmission_type": _("If you enter an invoice address, you also need to select an invoice "
                                            "transmission method.")}
                )

        vat_id_applicable = (
            'vat_id' in self.fields and
            data.get('is_business') and
            ask_for_vat_id(data.get('country'))
        )
        vat_id_required = vat_id_applicable and str(data.get('country')) in self.event.settings.invoice_address_vatid_required_countries
        if vat_id_required and not data.get('vat_id'):
            raise ValidationError({
                "vat_id": _("This field is required.")
            })

        if self.validate_vat_id and self.instance.vat_id_validated and 'vat_id' not in self.changed_data:
            pass  # Skip re-validation if it is validated
        elif self.validate_vat_id and vat_id_applicable:
            try:
                normalized_id = validate_vat_id(data.get('vat_id'), str(data.get('country')))
                self.instance.vat_id_validated = True
                self.instance.vat_id = data['vat_id'] = normalized_id
            except VATIDFinalError as e:
                if self.all_optional:
                    self.instance.vat_id_validated = False
                    messages.warning(self.request, e.message)
                else:
                    raise ValidationError({"vat_id": e.message})
            except VATIDTemporaryError as e:
                # We couldn't check it online, but we can still normalize it
                normalized_id = normalize_vat_id(data.get('vat_id'), str(data.get('country')))
                self.instance.vat_id = data['vat_id'] = normalized_id
                self.instance.vat_id_validated = False
                if self.request and self.vat_warning:
                    messages.warning(self.request, e.message)
        else:
            self.instance.vat_id_validated = False

        for transmission_type in get_transmission_types():
            if transmission_type.identifier == data.get("transmission_type"):
                if not transmission_type.is_available(self.event, data.get("country"), data.get("is_business")):
                    raise ValidationError({
                        "transmission_type": _("The selected transmission type is not available in your country or for "
                                               "your type of address.")
                    })

                required_fields = transmission_type.invoice_address_form_fields_required(data.get("country"), data.get("is_business"))
                for r in required_fields:
                    if r not in self.fields:
                        logger.info(f"Transmission type {transmission_type.identifier} required field {r} which is not available.")
                        raise ValidationError(
                            _("The selected type of invoice transmission requires a field that is currently not "
                              "available, please reach out to the organizer.")
                        )
                    if not data.get(r):
                        raise ValidationError({r: _("This field is required for the selected type of invoice transmission.")})

                self.instance.transmission_type = transmission_type.identifier
                self.instance.transmission_info = transmission_type.form_data_to_transmission_info(data)
            elif transmission_type.is_exclusive(self.event, data.get("country"), data.get("is_business")):
                if transmission_type.is_available(self.event, data.get("country"), data.get("is_business")):
                    raise ValidationError({
                        "transmission_type": "The transmission type '%s' must be used for this country or address type." % (
                            transmission_type.public_name,
                        )
                    })


class BaseInvoiceNameForm(BaseInvoiceAddressForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in list(self.fields.keys()):
            if f != 'name_parts':
                del self.fields[f]
