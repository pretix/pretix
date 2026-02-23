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
# This file contains Apache-licensed contributions copyrighted by: Alexey Kislitsin, Daniel, Heok Hong Low, Ian
# Williams, Jakob Schnell, Maico Timmerman, Sanket Dasgupta, Sohalt, Tobias Kunze, jasonwaiting@live.hk, luto,
# nelkenwelk, pajowu
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from decimal import Decimal
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import pycountry
from django import forms
from django.conf import settings
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db.models import Prefetch, Q, prefetch_related_objects
from django.forms import formset_factory, inlineformset_factory
from django.urls import reverse
from django.utils.functional import cached_property, lazy
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.timezone import get_current_timezone_name
from django.utils.translation import gettext, gettext_lazy as _, pgettext_lazy
from django_countries.fields import LazyTypedChoiceField
from django_scopes.forms import SafeModelMultipleChoiceField
from i18nfield.forms import (
    I18nForm, I18nFormField, I18nFormSetMixin, I18nTextarea, I18nTextInput,
)
from pytz import common_timezones

from pretix.base.forms import (
    I18nMarkdownTextarea, I18nModelForm, PlaceholderValidator, SettingsForm,
)
from pretix.base.models import Event, Organizer, TaxRule, Team
from pretix.base.models.event import EventFooterLink, EventMetaValue, SubEvent
from pretix.base.models.tax import TAX_CODE_LISTS
from pretix.base.reldate import RelativeDateField, RelativeDateTimeField
from pretix.base.services.placeholders import FormPlaceholderMixin
from pretix.base.settings import (
    COUNTRIES_WITH_STATE_IN_ADDRESS, COUNTRY_STATE_LABEL, DEFAULTS,
    PERSON_NAME_SCHEMES, PERSON_NAME_TITLE_GROUPS, ROUNDING_MODES,
    validate_event_settings,
)
from pretix.base.validators import multimail_validate
from pretix.control.forms import (
    MultipleLanguagesWidget, SalesChannelCheckboxSelectMultiple, SlugWidget,
    SplitDateTimeField, SplitDateTimePickerWidget,
)
from pretix.control.forms.widgets import Select2
from pretix.helpers.countries import CachedCountries
from pretix.multidomain.models import AlternativeDomainAssignment, KnownDomain
from pretix.multidomain.urlreverse import (
    build_absolute_uri, get_organizer_domain,
)
from pretix.plugins.banktransfer.payment import BankTransfer
from pretix.presale.style import get_fonts


class EventWizardFoundationForm(forms.Form):
    locales = forms.MultipleChoiceField(
        choices=settings.LANGUAGES,
        label=_("Use languages"),
        widget=MultipleLanguagesWidget,
        help_text=_('Choose all languages that your event should be available in.')
    )
    has_subevents = forms.BooleanField(
        label=_("This is an event series"),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        self.session = kwargs.pop('session')
        super().__init__(*args, **kwargs)
        qs = Organizer.objects.all()
        if not self.user.has_active_staff_session(self.session.session_key):
            qs = qs.filter(
                id__in=self.user.teams.filter(can_create_events=True).values_list('organizer', flat=True)
            )
        self.fields['organizer'] = forms.ModelChoiceField(
            label=_("Organizer"),
            queryset=qs,
            widget=Select2(
                attrs={
                    'data-model-select2': 'generic',
                    'data-select2-url': reverse('control:organizers.select2') + '?can_create=1',
                }
            ),
            empty_label=None,
            required=True
        )
        self.fields['organizer'].widget.choices = self.fields['organizer'].choices

        if len(self.fields['organizer'].choices) == 1:
            organizer = self.fields['organizer'].queryset.first()
            self.fields['organizer'].initial = organizer
            self.fields['locales'].initial = organizer.settings.locales


class EventWizardBasicsForm(I18nModelForm):
    error_messages = {
        'duplicate_slug': _("You already used this slug for a different event. Please choose a new one."),
    }
    timezone = forms.ChoiceField(
        choices=((a, a) for a in common_timezones),
        label=_("Event timezone"),
    )
    locale = forms.ChoiceField(
        choices=settings.LANGUAGES,
        label=_("Default language"),
    )
    no_taxes = forms.BooleanField(
        label=_("I don't want to specify taxes now"),
        help_text=_("You can always configure tax rates later."),
        required=False,
    )
    tax_rate = forms.DecimalField(
        label=_("Sales tax rate"),
        help_text=_("Do you need to pay sales tax on your tickets? In this case, please enter the applicable tax rate "
                    "here in percent. If you have a more complicated tax situation, you can add more tax rates and "
                    "detailed configuration later."),
        max_value=Decimal("100.00"),
        min_value=Decimal("0.00"),
        required=False
    )

    team = forms.ModelChoiceField(
        label=_("Grant access to team"),
        help_text=_("You are allowed to create events under this organizer, however you do not have permission "
                    "to edit all events under this organizer. Please select one of your existing teams that will"
                    " be granted access to this event."),
        queryset=Team.objects.none(),
        required=False,
        empty_label=_('Create a new team for this event with me as the only member')
    )

    class Meta:
        model = Event
        fields = [
            'name',
            'slug',
            'currency',
            'date_from',
            'date_to',
            'presale_start',
            'presale_end',
            'location',
            'is_remote',
            'geo_lat',
            'geo_lon',
        ]
        field_classes = {
            'date_from': SplitDateTimeField,
            'date_to': SplitDateTimeField,
            'presale_start': SplitDateTimeField,
            'presale_end': SplitDateTimeField,
        }
        widgets = {
            'date_from': SplitDateTimePickerWidget(),
            'date_to': SplitDateTimePickerWidget(attrs={'data-date-after': '#id_basics-date_from_0'}),
            'presale_start': SplitDateTimePickerWidget(),
            'presale_end': SplitDateTimePickerWidget(attrs={'data-date-after': '#id_basics-presale_start_0'}),
            'slug': SlugWidget,
        }

    def __init__(self, *args, **kwargs):
        self.organizer = kwargs.pop('organizer')
        self.locales = kwargs.get('locales')
        self.has_subevents = kwargs.pop('has_subevents')
        self.user = kwargs.pop('user')
        self.session = kwargs.pop('session')
        super().__init__(*args, **kwargs)
        if 'timezone' not in self.initial:
            self.initial['timezone'] = get_current_timezone_name()
        self.fields['locale'].choices = [(a, b) for a, b in settings.LANGUAGES if a in self.locales]
        self.fields['location'].widget.attrs['rows'] = '3'
        self.fields['location'].widget.attrs['placeholder'] = _(
            'Sample Conference Center\nHeidelberg, Germany'
        )
        self.fields['slug'].widget.prefix = build_absolute_uri(self.organizer, 'presale:organizer.index')
        self.fields['tax_rate']._required = True  # Do not render as optional because it is conditionally required
        if self.has_subevents:
            del self.fields['presale_start']
            del self.fields['presale_end']
            del self.fields['date_to']

        if self.has_control_rights(self.user, self.organizer, self.session):
            del self.fields['team']
        else:
            self.fields['team'].queryset = self.user.teams.filter(organizer=self.organizer)
            if self.organizer.pk and not self.organizer.settings.get("event_team_provisioning", True, as_type=bool):
                self.fields['team'].required = True
                self.fields['team'].empty_label = None
                self.fields['team'].initial = 0

    def clean(self):
        data = super().clean()
        if data.get('locale') not in self.locales:
            raise ValidationError({
                'locale': _('Your default locale must also be enabled for your event (see box above).')
            })
        if data.get('timezone') not in common_timezones:
            raise ValidationError({
                'timezone': _('Your default locale must be specified.')
            })
        if not data.get("no_taxes") and data.get("tax_rate") is None:
            raise ValidationError({
                'tax_rate': _('You have not specified a tax rate. If you do not want us to compute sales taxes, please '
                              'check "{field}" above.').format(field=self.fields["no_taxes"].label)
            })

        # change timezone
        zone = ZoneInfo(data.get('timezone'))
        data['date_from'] = self.reset_timezone(zone, data.get('date_from'))
        data['date_to'] = self.reset_timezone(zone, data.get('date_to'))
        data['presale_start'] = self.reset_timezone(zone, data.get('presale_start'))
        data['presale_end'] = self.reset_timezone(zone, data.get('presale_end'))
        return data

    @staticmethod
    def reset_timezone(tz, dt):
        return dt.replace(tzinfo=tz) if dt is not None else None

    def clean_slug(self):
        slug = self.cleaned_data['slug']
        if Event.objects.filter(slug__iexact=slug, organizer=self.organizer).exists():
            raise forms.ValidationError(
                self.error_messages['duplicate_slug'],
                code='duplicate_slug'
            )
        return slug

    @staticmethod
    def has_control_rights(user, organizer, session):
        return user.teams.filter(
            organizer=organizer, all_events=True, can_change_event_settings=True, can_change_items=True,
            can_change_orders=True, can_change_vouchers=True
        ).exists() or user.has_active_staff_session(session.session_key)


class EventChoiceMixin:
    def label_from_instance(self, obj):
        return mark_safe('{}<br /><span class="text-muted">{} · {}</span>'.format(
            escape(str(obj)),
            obj.get_date_range_display() if not obj.has_subevents else _("Event series"),
            obj.slug
        ))


class EventChoiceField(forms.ModelChoiceField):
    pass


class SafeEventMultipleChoiceField(EventChoiceMixin, forms.ModelMultipleChoiceField):
    def __init__(self, queryset, *args, **kwargs):
        queryset = queryset.model.objects.none()
        super().__init__(queryset, *args, **kwargs)


class EventWizardCopyForm(forms.Form):

    @staticmethod
    def copy_from_queryset(user, session):
        if user.has_active_staff_session(session.session_key):
            return Event.objects.all()
        return Event.objects.filter(
            Q(organizer_id__in=user.teams.filter(
                all_events=True, can_change_event_settings=True, can_change_items=True
            ).values_list('organizer', flat=True)) | Q(id__in=user.teams.filter(
                can_change_event_settings=True, can_change_items=True
            ).values_list('limit_events__id', flat=True))
        )

    def __init__(self, *args, **kwargs):
        kwargs.pop('organizer')
        kwargs.pop('locales')
        self.session = kwargs.pop('session')
        kwargs.pop('has_subevents')
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

        self.fields['copy_from_event'] = EventChoiceField(
            label=_("Copy configuration from"),
            queryset=EventWizardCopyForm.copy_from_queryset(self.user, self.session),
            widget=Select2(
                attrs={
                    'data-model-select2': 'event',
                    'data-select2-url': reverse('control:events.typeahead') + '?can_copy=1',
                    'data-placeholder': _('Do not copy')
                }
            ),
            empty_label=_('Do not copy'),
            required=False
        )
        self.fields['copy_from_event'].widget.choices = self.fields['copy_from_event'].choices


class EventMetaValueForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        self.property = kwargs.pop('property')
        self.disabled = kwargs.pop('disabled')
        super().__init__(*args, **kwargs)
        if self.property.choices:
            self.fields['value'] = forms.ChoiceField(
                label=self.property.name,
                choices=[
                    ('', _('Default ({value})').format(value=self.property.default) if self.property.default else ''),
                ] + [(a.strip(), a.strip()) for a in self.property.choice_keys],
            )
        else:
            self.fields['value'].label = self.property.name
            self.fields['value'].widget.attrs['placeholder'] = self.property.default
            self.fields['value'].widget.attrs['data-typeahead-url'] = (
                reverse('control:events.meta.typeahead') + '?' + urlencode({
                    'property': self.property.name,
                    'organizer': self.property.organizer.slug,
                })
            )
        self.fields['value'].required = False
        if self.disabled:
            self.fields['value'].widget.attrs['readonly'] = 'readonly'

    def clean_slug(self):
        if self.disabled:
            return self.instance.value if self.instance else None
        return self.cleaned_data['slug']

    class Meta:
        model = EventMetaValue
        fields = ['value']
        widgets = {
            'value': forms.TextInput()
        }


class EventUpdateForm(I18nModelForm):

    def __init__(self, *args, **kwargs):
        self.change_slug = kwargs.pop('change_slug', False)

        kwargs.setdefault('initial', {})
        self.instance = kwargs['instance']

        super().__init__(*args, **kwargs)
        if not self.change_slug:
            self.fields['slug'].widget.attrs['readonly'] = 'readonly'

        if self.instance.orders.exists():
            self.fields['currency'].disabled = True
            self.fields['currency'].help_text = _(
                'The currency cannot be changed because orders already exist.'
            )

        self.fields['location'].widget.attrs['rows'] = '3'
        self.fields['location'].widget.attrs['placeholder'] = _(
            'Sample Conference Center\nHeidelberg, Germany'
        )

        try:
            self.fields['domain'] = forms.CharField(
                max_length=255,
                label=_('Domain'),
                initial=self.instance.domain.domainname,
                required=False,
                disabled=True,
                help_text=_('You can configure this in your organizer settings.')
            )
        except KnownDomain.DoesNotExist:
            domain = get_organizer_domain(self.instance.organizer)
            try:
                current_domain_assignment = self.instance.alternative_domain_assignment
            except AlternativeDomainAssignment.DoesNotExist:
                current_domain_assignment = None
            self.fields['domain'] = forms.ChoiceField(
                label=_('Domain'),
                help_text=_('You can add more domains in your organizer account.'),
                choices=[('', _('Same as organizer account') + (f" ({domain})" if domain else ""))] + [
                    (d.domainname, d.domainname) for d in self.instance.organizer.domains.filter(mode=KnownDomain.MODE_ORG_ALT_DOMAIN)
                ],
                initial=current_domain_assignment.domain_id if current_domain_assignment else "",
                required=False,
            )
        self.fields['limit_sales_channels'].queryset = self.event.organizer.sales_channels.all()
        self.fields['limit_sales_channels'].widget = SalesChannelCheckboxSelectMultiple(self.event, attrs={
            'data-inverse-dependency': '<[name$=all_sales_channels]',
        }, choices=self.fields['limit_sales_channels'].widget.choices)

    def save(self, commit=True):
        instance = super().save(commit)

        try:
            current_domain_assignment = instance.alternative_domain_assignment
        except AlternativeDomainAssignment.DoesNotExist:
            current_domain_assignment = None
        if self.cleaned_data['domain'] and not hasattr(instance, 'domain'):
            domain = self.instance.organizer.domains.get(mode=KnownDomain.MODE_ORG_ALT_DOMAIN, domainname=self.cleaned_data["domain"])
            AlternativeDomainAssignment.objects.update_or_create(
                event=instance,
                defaults={
                    "domain": domain,
                }
            )
            instance.cache.clear()
        elif current_domain_assignment:
            current_domain_assignment.delete()
            instance.cache.clear()

        return instance

    def clean_slug(self):
        if self.change_slug:
            return self.cleaned_data['slug']
        return self.instance.slug

    class Meta:
        model = Event
        localized_fields = '__all__'
        fields = [
            'name',
            'slug',
            'currency',
            'date_from',
            'date_to',
            'date_admission',
            'is_public',
            'presale_start',
            'presale_end',
            'location',
            'is_remote',
            'geo_lat',
            'geo_lon',
            'all_sales_channels',
            'limit_sales_channels',
        ]
        field_classes = {
            'date_from': SplitDateTimeField,
            'date_to': SplitDateTimeField,
            'date_admission': SplitDateTimeField,
            'presale_start': SplitDateTimeField,
            'presale_end': SplitDateTimeField,
            'limit_sales_channels': SafeModelMultipleChoiceField,
        }
        widgets = {
            'date_from': SplitDateTimePickerWidget(),
            'date_to': SplitDateTimePickerWidget(attrs={'data-date-after': '#id_date_from_0'}),
            'date_admission': SplitDateTimePickerWidget(attrs={'data-date-default': '#id_date_from_0'}),
            'presale_start': SplitDateTimePickerWidget(),
            'presale_end': SplitDateTimePickerWidget(attrs={'data-date-after': '#id_presale_start_0'}),
        }


class EventSettingsValidationMixin:

    def clean(self):
        data = super().clean()
        settings_dict = self.obj.settings.freeze()
        settings_dict.update(data)
        validate_event_settings(self.obj, settings_dict)
        return data

    def add_error(self, field, error):
        # Copied from Django, but with improved handling for validation errors on fields that are not part of this form

        if not isinstance(error, ValidationError):
            error = ValidationError(error)

        if hasattr(error, 'error_dict'):
            if field is not None:
                raise TypeError(
                    "The argument `field` must be `None` when the `error` "
                    "argument contains errors for multiple fields."
                )
            else:
                error = error.error_dict
        else:
            error = {field or NON_FIELD_ERRORS: error.error_list}

        for field, error_list in error.items():
            if field != NON_FIELD_ERRORS and field not in self.fields:
                field = NON_FIELD_ERRORS
                for e in error_list:
                    e.message = _('A validation error has occurred on a setting that is not part of this form: {error}').format(error=e.message)

            if field not in self.errors:
                if field == NON_FIELD_ERRORS:
                    self._errors[field] = self.error_class(error_class='nonfield')
                else:
                    self._errors[field] = self.error_class()
            self._errors[field].extend(error_list)
            if field in self.cleaned_data:
                del self.cleaned_data[field]


class EventSettingsForm(EventSettingsValidationMixin, FormPlaceholderMixin, SettingsForm):
    timezone = forms.ChoiceField(
        choices=((a, a) for a in common_timezones),
        label=_("Event timezone"),
    )
    name_scheme = forms.ChoiceField(
        label=_("Name format"),
        help_text=_("This defines how pretix will ask for human names. Changing this after you already received "
                    "orders might lead to unexpected behavior when sorting or changing names."),
        required=True,
    )
    name_scheme_titles = forms.ChoiceField(
        label=_("Allowed titles"),
        help_text=_("If the naming scheme you defined above allows users to input a title, you can use this to "
                    "restrict the set of selectable titles."),
        required=False,
    )

    auto_fields = [
        'imprint_url',
        'checkout_email_helptext',
        'presale_has_ended_text',
        'voucher_explanation_text',
        'checkout_success_text',
        'show_dates_on_frontpage',
        'show_date_to',
        'show_times',
        'show_items_outside_presale_period',
        'hide_prices_from_attendees',
        'presale_start_show_date',
        'locales',
        'locale',
        'region',
        'show_quota_left',
        'waiting_list_enabled',
        'waiting_list_auto_disable',
        'waiting_list_hours',
        'waiting_list_auto',
        'waiting_list_names_asked',
        'waiting_list_names_required',
        'waiting_list_phones_asked',
        'waiting_list_phones_required',
        'waiting_list_phones_explanation_text',
        'waiting_list_limit_per_user',
        'max_items_per_order',
        'reservation_time',
        'contact_mail',
        'show_variations_expanded',
        'hide_sold_out',
        'meta_noindex',
        'redirect_to_checkout_directly',
        'frontpage_subevent_ordering',
        'low_availability_percentage',
        'event_list_type',
        'event_list_available_only',
        'event_list_filters',
        'event_calendar_future_only',
        'frontpage_text',
        'event_info_text',
        'attendee_names_asked',
        'attendee_names_required',
        'attendee_emails_asked',
        'attendee_emails_required',
        'attendee_company_asked',
        'attendee_company_required',
        'attendee_addresses_asked',
        'attendee_addresses_required',
        'attendee_data_explanation_text',
        'order_phone_asked',
        'order_phone_required',
        'checkout_phone_helptext',
        'banner_text',
        'banner_text_bottom',
        'order_email_asked_twice',
        'allow_modifications',
        'last_order_modification_date',
        'allow_modifications_after_checkin',
        'checkout_show_copy_answers_button',
        'show_checkin_number_user',
        'primary_color',
        'theme_color_success',
        'theme_color_danger',
        'theme_color_background',
        'theme_round_borders',
        'primary_font',
        'logo_image',
        'logo_image_large',
        'logo_show_title',
        'og_image',
    ]

    base_context = {
        'frontpage_text': ['event'],
    }

    def _resolve_virtual_keys_input(self, data, prefix=''):
        # set all dependants of virtual_keys and
        # delete all virtual_fields to prevent them from being saved
        for virtual_key in self.virtual_keys:
            if prefix + virtual_key not in data:
                continue
            base_key = prefix + virtual_key.rsplit('_', 2)[0]
            asked_key = base_key + '_asked'
            required_key = base_key + '_required'

            if data[prefix + virtual_key] == 'optional':
                data[asked_key] = True
                data[required_key] = False
            elif data[prefix + virtual_key] == 'required':
                data[asked_key] = True
                data[required_key] = True
            # Explicitly check for 'do_not_ask'.
            # Do not overwrite as default-behaviour when no value for virtual field is transmitted!
            elif data[prefix + virtual_key] == 'do_not_ask':
                data[asked_key] = False
                data[required_key] = False

            # hierarkey.forms cannot handle non-existent keys in cleaned_data => do not delete, but set to None
            if not prefix:
                data[virtual_key] = None
        return data

    def clean(self):
        self.cleaned_data = self._resolve_virtual_keys_input(self.cleaned_data)
        data = super().clean()
        return data

    def __init__(self, *args, **kwargs):
        self.event = kwargs['obj']
        super().__init__(*args, **kwargs)
        self.fields['name_scheme'].choices = (
            (k, _('Ask for {fields}, display like {example}').format(
                fields=' + '.join(str(vv[1]) for vv in v['fields']),
                example=v['concatenation'](v['sample'])
            ))
            for k, v in PERSON_NAME_SCHEMES.items()
        )
        self.fields['name_scheme_titles'].choices = [('', _('Free text input'))] + [
            (k, '{scheme}: {samples}'.format(
                scheme=v[0],
                samples=', '.join(v[1])
            ) if v[0] != ', '.join(v[1]) else v[0])
            for k, v in PERSON_NAME_TITLE_GROUPS.items()
        ]
        if not self.event.has_subevents:
            del self.fields['frontpage_subevent_ordering']
            del self.fields['event_list_type']
            del self.fields['event_list_available_only']
            del self.fields['event_list_filters']
            del self.fields['event_calendar_future_only']
        self.fields['primary_font'].choices = [('Open Sans', 'Open Sans')] + sorted([
            (a, {"title": a, "data": v}) for a, v in get_fonts(self.event, pdf_support_required=False).items()
        ], key=lambda a: a[0])

        # create "virtual" fields for better UX when editing <name>_asked and <name>_required fields
        self.virtual_keys = []
        for asked_key in [key for key in self.fields.keys() if key.endswith('_asked')]:
            required_key = asked_key.rsplit('_', 1)[0] + '_required'
            virtual_key = asked_key + '_required'
            if required_key not in self.fields or virtual_key in self.fields:
                # either no matching required key or
                # there already is a field with virtual_key defined manually, so do not overwrite
                continue

            asked_field = self.fields[asked_key]

            self.fields[virtual_key] = forms.ChoiceField(
                label=asked_field.label,
                help_text=asked_field.help_text,
                required=True,
                widget=forms.RadioSelect,
                choices=[
                    # default key needs a value other than '' because with '' it would also overwrite even if combi-field is not transmitted
                    ('do_not_ask', _('Do not ask')),
                    ('optional', _('Ask, but do not require input')),
                    ('required', _('Ask and require input'))
                ]
            )
            self.virtual_keys.append(virtual_key)

            if self.initial[required_key]:
                self.initial[virtual_key] = 'required'
            elif self.initial[asked_key]:
                self.initial[virtual_key] = 'optional'
            else:
                self.initial[virtual_key] = 'do_not_ask'

        for k, v in self.base_context.items():
            self._set_field_placeholders(k, v)

    @cached_property
    def changed_data(self):
        data = []

        # We need to resolve the mapping between our "virtual" fields and the "real"fields here, otherwise
        # they are detected as "changed" on every save even though they aren't.
        in_data = self._resolve_virtual_keys_input(self.data.copy(), prefix=f'{self.prefix}-' if self.prefix else '')

        for name, field in self.fields.items():
            prefixed_name = self.add_prefix(name)
            data_value = field.widget.value_from_datadict(in_data, self.files, prefixed_name)
            if not field.show_hidden_initial:
                # Use the BoundField's initial as this is the value passed to
                # the widget.
                initial_value = self[name].initial
            else:
                initial_prefixed_name = self.add_initial_prefix(name)
                hidden_widget = field.hidden_widget()
                try:
                    initial_value = field.to_python(hidden_widget.value_from_datadict(
                        self.data, self.files, initial_prefixed_name))
                except ValidationError:
                    # Always assume data has changed if validation fails.
                    data.append(name)
                    continue
            if field.has_changed(initial_value, data_value):
                data.append(name)
        return data


class CancelSettingsForm(SettingsForm):
    auto_fields = [
        'cancel_allow_user',
        'cancel_allow_user_until',
        'cancel_allow_user_paid',
        'cancel_allow_user_paid_until',
        'cancel_allow_user_unpaid_keep',
        'cancel_allow_user_unpaid_keep_fees',
        'cancel_allow_user_unpaid_keep_percentage',
        'cancel_allow_user_paid_keep',
        'cancel_allow_user_paid_keep_fees',
        'cancel_allow_user_paid_keep_percentage',
        'cancel_allow_user_paid_adjust_fees',
        'cancel_allow_user_paid_adjust_fees_explanation',
        'cancel_allow_user_paid_adjust_fees_step',
        'cancel_allow_user_paid_refund_as_giftcard',
        'cancel_allow_user_paid_require_approval',
        'cancel_allow_user_paid_require_approval_fee_unknown',
        'cancel_terms_paid',
        'cancel_terms_unpaid',
        'change_allow_user_variation',
        'change_allow_user_price',
        'change_allow_user_until',
        'change_allow_user_addons',
        'change_allow_user_if_checked_in',
        'change_allow_attendee',
        'tax_rule_cancellation',
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.obj.settings.giftcard_expiry_years is not None:
            self.fields['cancel_allow_user_paid_refund_as_giftcard'].help_text = gettext(
                'You have configured gift cards to be valid {} years plus the year the gift card is issued in.'
            ).format(self.obj.settings.giftcard_expiry_years)


class PaymentSettingsForm(EventSettingsValidationMixin, SettingsForm):
    auto_fields = [
        'payment_term_mode',
        'payment_term_days',
        'payment_term_weekdays',
        'payment_term_minutes',
        'payment_term_last',
        'payment_term_expire_automatically',
        'payment_term_expire_delay_days',
        'payment_term_accept_late',
        'payment_pending_hidden',
        'payment_explanation',
        'tax_rule_payment',
    ]

    def clean_payment_term_days(self):
        value = self.cleaned_data.get('payment_term_days')
        if self.cleaned_data.get('payment_term_mode') == 'days' and value is None:
            raise ValidationError(_("This field is required."))
        return value

    def clean_payment_term_minutes(self):
        value = self.cleaned_data.get('payment_term_minutes')
        if self.cleaned_data.get('payment_term_mode') == 'minutes' and value is None:
            raise ValidationError(_("This field is required."))
        return value


class DisplayNetPricesBooleanSelect(forms.RadioSelect):
    def __init__(self, attrs=None):
        choices = (
            ("false", format_html(
                '{} <br><span class="text-muted">{}</span>',
                _("Prices including tax"),
                _("Recommended if you sell tickets at least partly to consumers.")
            )),
            ("true", format_html(
                '{} <br><span class="text-muted">{}</span>',
                _("Prices excluding tax"),
                _("Recommended only if you sell tickets primarily to business customers.")
            )),
        )
        super().__init__(attrs, choices)

    def format_value(self, value):
        try:
            return {
                True: "true",
                False: "false",
                "true": "true",
                "false": "false",
            }[value]
        except KeyError:
            return "unknown"

    def value_from_datadict(self, data, files, name):
        value = data.get(name)
        return {
            True: True,
            "True": True,
            "False": False,
            False: False,
            "true": True,
            "false": False,
        }.get(value)


class TaxSettingsForm(EventSettingsValidationMixin, SettingsForm):
    auto_fields = [
        'display_net_prices',
        'tax_rounding',
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["display_net_prices"].label = _("Prices shown to customer")
        self.fields["display_net_prices"].widget = DisplayNetPricesBooleanSelect()
        help_text = {
            "line": _(
                "Recommended when e-invoicing is not required. Each product will be sold with the advertised "
                "net and gross price. However, in orders of more than one product, the total tax amount "
                "can differ from when it would be computed from the order total."
            ),
            "sum_by_net": _(
                "Recommended for e-invoicing when you primarily sell to business customers and "
                "show prices to customers excluding tax. "
                "The gross price of some products may be changed to ensure correct rounding, while the net "
                "prices will be kept as configured. This may cause the actual payment amount to differ."
            ),
            "sum_by_net_only_business": _(
                "Same as above, but only applied to business customers. Line-based rounding will be used for consumers. "
                "Recommended when e-invoicing is only used for business customers and consumers do not receive "
                "invoices. This can cause the payment amount to change when the invoice address is changed."
            ),
            "sum_by_net_keep_gross": _(
                "Recommended for e-invoicing when you primarily sell to consumers. "
                "The gross or net price of some products may be changed automatically to ensure correct "
                "rounding of the order total. The system attempts to keep gross prices as configured whenever "
                "possible. Gross prices may still change if they are impossible to derive from a rounded net price."
            ),
        }
        self.fields["tax_rounding"].choices = (
            (k, format_html('{}<br><span class="text-muted">{}</span>', v, help_text.get(k, "")))
            for k, v in ROUNDING_MODES
        )


class ProviderForm(SettingsForm):
    """
    This is a SettingsForm, but if fields are set to required=True, validation
    errors are only raised if the payment method is enabled.
    """

    def __init__(self, *args, **kwargs):
        self.settingspref = kwargs.pop('settingspref')
        self.provider = kwargs.pop('provider', None)
        super().__init__(*args, **kwargs)

    def prepare_fields(self):
        for k, v in self.fields.items():
            v._required = v.required
            v.required = False
            v.widget.is_required = False
            if isinstance(v, I18nFormField):
                v._required = v.one_required
                v.one_required = False
                v.widget.enabled_locales = self.locales
            elif isinstance(v, (RelativeDateTimeField, RelativeDateField)):
                v.set_event(self.obj)

            if hasattr(v, '_as_type'):
                self.initial[k] = self.obj.settings.get(k, as_type=v._as_type, default=v.initial)

    def clean(self):
        cleaned_data = super().clean()
        enabled = cleaned_data.get(self.settingspref + '_enabled')
        if not enabled:
            return
        if cleaned_data.get(self.settingspref + '_hidden_url', None):
            cleaned_data[self.settingspref + '_hidden_url'] = None
        for k, v in self.fields.items():
            val = cleaned_data.get(k)
            if v._required and not val:
                self.add_error(k, _('This field is required.'))
        if self.provider:
            cleaned_data = self.provider.settings_form_clean(cleaned_data)
        return cleaned_data


class InvoiceSettingsForm(EventSettingsValidationMixin, SettingsForm):

    auto_fields = [
        'invoice_address_asked',
        'invoice_address_required',
        'invoice_address_vatid',
        'invoice_address_vatid_required_countries',
        'invoice_address_company_required',
        'invoice_address_beneficiary',
        'invoice_address_custom_field',
        'invoice_address_custom_field_helptext',
        'invoice_name_required',
        'invoice_address_not_asked_free',
        'invoice_include_free',
        'invoice_show_payments',
        'invoice_reissue_after_modify',
        'invoice_generate',
        'invoice_generate_only_business',
        'invoice_period',
        'invoice_attendee_name',
        'invoice_event_location',
        'invoice_include_expire_date',
        'invoice_numbers_consecutive',
        'invoice_numbers_prefix',
        'invoice_numbers_prefix_cancellations',
        'invoice_numbers_counter_length',
        'invoice_address_explanation_text',
        'invoice_email_attachment',
        'invoice_email_organizer',
        'invoice_address_from_name',
        'invoice_address_from',
        'invoice_address_from_zipcode',
        'invoice_address_from_city',
        'invoice_address_from_state',
        'invoice_address_from_country',
        'invoice_address_from_tax_id',
        'invoice_address_from_vat_id',
        'invoice_introductory_text',
        'invoice_additional_text',
        'invoice_footer_text',
        'invoice_eu_currencies',
        'invoice_logo_image',
        'invoice_renderer_highlight_order_code',
        'invoice_renderer_font',
    ]

    invoice_generate_sales_channels = forms.MultipleChoiceField(
        label=_('Generate invoices for Sales channels'),
        choices=[],
        widget=forms.CheckboxSelectMultiple,
        help_text=_("If you have enabled invoice generation in the previous setting, you can limit it here to specific "
                    "sales channels.")
    )
    invoice_renderer = forms.ChoiceField(
        label=_("Invoice style"),
        required=True,
        choices=[]
    )
    invoice_language = forms.ChoiceField(
        widget=forms.Select, required=True,
        label=_("Invoice language"),
        choices=[('__user__', _('The user\'s language'))] + settings.LANGUAGES,
    )

    def __init__(self, *args, **kwargs):
        event = kwargs.get('obj')
        super().__init__(*args, **kwargs)
        self.fields['invoice_renderer'].choices = [
            (r.identifier, r.verbose_name) for r in event.get_invoice_renderers().values()
        ]
        self.fields['invoice_numbers_prefix'].widget.attrs['placeholder'] = event.slug.upper() + '-'
        if event.settings.invoice_numbers_prefix:
            self.fields['invoice_numbers_prefix_cancellations'].widget.attrs['placeholder'] = event.settings.invoice_numbers_prefix
        else:
            self.fields['invoice_numbers_prefix_cancellations'].widget.attrs['placeholder'] = event.slug.upper() + '-'
        locale_names = dict(settings.LANGUAGES)
        self.fields['invoice_language'].choices = [('__user__', _('The user\'s language'))] + [(a, locale_names[a]) for a in event.settings.locales]
        self.fields['invoice_generate_sales_channels'].choices = (
            (c.identifier, c.label) for c in event.organizer.sales_channels.all()
        )
        pps = [str(pp.verbose_name) for pp in event.get_payment_providers().values() if pp.requires_invoice_immediately]
        if pps:
            generate_paid_help_text = _('An invoice will be issued before payment if the customer selects one of the following payment methods: {list}').format(
                list=', '.join(pps)
            )
        else:
            generate_paid_help_text = _('None of the currently configured payment methods will cause an invoice to be issued before payment.')

        generate_choices = list(DEFAULTS['invoice_generate']['form_kwargs']['choices'])
        idx = [i for i, t in enumerate(generate_choices) if t[0] == 'paid'][0]
        generate_choices[idx] = (
            'paid',
            format_html(
                '{} <span class="label label-success">{}</span><br><span class="text-muted">{}</span>',
                generate_choices[idx][1],
                _('Recommended'),
                generate_paid_help_text
            )
        )
        self.fields['invoice_generate'].choices = generate_choices
        self.fields['invoice_renderer_font'].choices += [
            (a, a) for a in get_fonts(event, pdf_support_required=True).keys()
        ]

        if 'invoice_address_from_country' in self.data:
            cc = str(self.data['invoice_address_from_country'])
        elif 'invoice_address_from_country' in self.initial:
            cc = str(self.initial['invoice_address_from_country'])
        else:
            cc = self.obj.settings.invoice_address_from_country
        c = [('', '---')]
        state_label = pgettext_lazy('address', 'State')
        if cc and cc in COUNTRIES_WITH_STATE_IN_ADDRESS:
            types, form = COUNTRIES_WITH_STATE_IN_ADDRESS[cc]
            statelist = [s for s in pycountry.subdivisions.get(country_code=cc) if s.type in types]
            c += sorted([(s.code[3:], s.name) for s in statelist], key=lambda s: s[1])
            if cc in COUNTRY_STATE_LABEL:
                state_label = COUNTRY_STATE_LABEL[cc]
        elif 'invoice_address_from_state' in self.data:
            self.data = self.data.copy()
            del self.data['invoice_address_from_state']
        self.fields['invoice_address_from_state'].choices = c
        self.fields['invoice_address_from_state'].label = state_label


def contains_web_channel_validate(val):
    if "web" not in val:
        raise ValidationError(_("The online shop must be selected to receive these emails."))


class MailSettingsForm(FormPlaceholderMixin, SettingsForm):
    auto_fields = [
        'mail_prefix',
        'mail_from_name',
        'mail_attach_ical',
        'mail_attach_tickets',
        'mail_attachment_new_order',
        'mail_attach_ical_paid_only',
        'mail_attach_ical_description',
    ]

    mail_sales_channel_placed_paid = forms.MultipleChoiceField(
        choices=[],
        label=_('Sales channels for checkout emails'),
        help_text=_('The order placed and paid emails will only be send to orders from these sales channels. '
                    'The online shop must be enabled.'),
        widget=forms.CheckboxSelectMultiple(
            attrs={'class': 'scrolling-multiple-choice'}
        ),
        validators=[contains_web_channel_validate],
    )

    mail_sales_channel_download_reminder = forms.MultipleChoiceField(
        choices=[],
        label=_('Sales channels'),
        help_text=_('This email will only be send to orders from these sales channels. The online shop must be enabled.'),
        widget=forms.CheckboxSelectMultiple(
            attrs={'class': 'scrolling-multiple-choice'}
        ),
        validators=[contains_web_channel_validate],
    )

    mail_bcc = forms.CharField(
        label=_("Bcc address"),
        help_text=' '.join([
            str(_("All emails will be sent to this address as a Bcc copy.")),
            str(_("You can specify multiple recipients separated by commas.")),
        ]),
        validators=[multimail_validate],
        required=False,
        max_length=255
    )
    mail_text_signature = I18nFormField(
        label=_("Signature"),
        required=False,
        widget=I18nMarkdownTextarea,
        help_text=_("This will be attached to every email. Available placeholders: {event}"),
        validators=[PlaceholderValidator(['{event}'])],
        widget_kwargs={'attrs': {
            'rows': '4',
            'placeholder': _(
                'e.g. your contact details'
            )
        }}
    )
    mail_html_renderer = forms.ChoiceField(
        label=_("HTML mail renderer"),
        required=True,
        choices=[]
    )
    mail_subject_order_placed = I18nFormField(
        label=_("Subject sent to order contact address"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_order_placed = I18nFormField(
        label=_("Text sent to order contact address"),
        required=False,
        widget=I18nMarkdownTextarea,
    )
    mail_send_order_placed_attendee = forms.BooleanField(
        label=_("Send an email to attendees"),
        help_text=_('If the order contains attendees with email addresses different from the person who orders the '
                    'tickets, the following email will be sent out to the attendees.'),
        required=False,
    )
    mail_subject_order_placed_attendee = I18nFormField(
        label=_("Subject sent to attendees"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_order_placed_attendee = I18nFormField(
        label=_("Text sent to attendees"),
        required=False,
        widget=I18nMarkdownTextarea,
    )

    mail_subject_order_paid = I18nFormField(
        label=_("Subject sent to order contact address"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_order_paid = I18nFormField(
        label=_("Text sent to order contact address"),
        required=False,
        widget=I18nMarkdownTextarea,
    )
    mail_send_order_paid_attendee = forms.BooleanField(
        label=_("Send an email to attendees"),
        help_text=_('If the order contains attendees with email addresses different from the person who orders the '
                    'tickets, the following email will be sent out to the attendees.'),
        required=False,
    )
    mail_subject_order_paid_attendee = I18nFormField(
        label=_("Subject sent to attendees"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_order_paid_attendee = I18nFormField(
        label=_("Text sent to attendees"),
        required=False,
        widget=I18nMarkdownTextarea,
    )

    mail_subject_order_free = I18nFormField(
        label=_("Subject sent to order contact address"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_order_free = I18nFormField(
        label=_("Text sent to order contact address"),
        required=False,
        widget=I18nMarkdownTextarea,
    )
    mail_send_order_free_attendee = forms.BooleanField(
        label=_("Send an email to attendees"),
        help_text=_('If the order contains attendees with email addresses different from the person who orders the '
                    'tickets, the following email will be sent out to the attendees.'),
        required=False,
    )
    mail_subject_order_free_attendee = I18nFormField(
        label=_("Subject sent to attendees"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_order_free_attendee = I18nFormField(
        label=_("Text sent to attendees"),
        required=False,
        widget=I18nMarkdownTextarea,
    )

    mail_subject_order_changed = I18nFormField(
        label=_("Subject"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_order_changed = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nMarkdownTextarea,
    )
    mail_subject_resend_link = I18nFormField(
        label=_("Subject (sent by admin)"),
        required=False,
        widget=I18nTextInput,
    )
    mail_subject_resend_link_attendee = I18nFormField(
        label=_("Subject (sent by admin to attendee)"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_resend_link = I18nFormField(
        label=_("Text (sent by admin)"),
        required=False,
        widget=I18nMarkdownTextarea,
    )
    mail_subject_resend_all_links = I18nFormField(
        label=_("Subject (requested by user)"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_resend_all_links = I18nFormField(
        label=_("Text (requested by user)"),
        required=False,
        widget=I18nMarkdownTextarea,
    )
    mail_days_order_expire_warning = forms.IntegerField(
        label=_("Number of days"),
        required=True,
        min_value=0,
        help_text=_("This email will be sent out this many days before the order expires. If the "
                    "value is 0, the mail will never be sent.")
    )
    mail_text_order_expire_warning = I18nFormField(
        label=_("Text (if order will expire automatically)"),
        required=False,
        widget=I18nMarkdownTextarea,
    )
    mail_subject_order_expire_warning = I18nFormField(
        label=_("Subject (if order will expire automatically)"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_order_pending_warning = I18nFormField(
        label=_("Text (if order will not expire automatically)"),
        required=False,
        widget=I18nMarkdownTextarea,
    )
    mail_subject_order_pending_warning = I18nFormField(
        label=_("Subject (if order will not expire automatically)"),
        required=False,
        widget=I18nTextInput,
    )
    mail_subject_order_incomplete_payment = I18nFormField(
        label=_("Subject (if an incomplete payment was received)"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_order_incomplete_payment = I18nFormField(
        label=_("Text (if an incomplete payment was received)"),
        required=False,
        widget=I18nMarkdownTextarea,
        help_text=_("This email only applies to payment methods that can receive incomplete payments, "
                    "such as bank transfer."),
    )
    mail_subject_order_payment_failed = I18nFormField(
        label=_("Subject"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_order_payment_failed = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nMarkdownTextarea,
    )
    mail_subject_waiting_list = I18nFormField(
        label=_("Subject"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_waiting_list = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nMarkdownTextarea,
    )
    mail_subject_order_canceled = I18nFormField(
        label=_("Subject"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_order_canceled = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nMarkdownTextarea,
    )
    mail_text_order_custom_mail = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nMarkdownTextarea,
    )
    mail_subject_order_invoice = I18nFormField(
        label=_("Subject"),
        required=False,
        widget=I18nTextInput,
        help_text=_("This will only be used if the invoice is sent to a different email address or at a different time "
                    "than the order confirmation."),
    )
    mail_text_order_invoice = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nTextarea,  # no Markdown supported
        help_text=lazy(
            lambda: str(_(
                "This will only be used if the invoice is sent to a different email address or at a different time "
                "than the order confirmation."
            )) + " " + str(_(
                "Formatting is not supported, as some accounting departments process mail automatically and do not "
                "handle formatted emails properly."
            )),
            str
        )()
    )
    mail_subject_download_reminder = I18nFormField(
        label=_("Subject sent to order contact address"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_download_reminder = I18nFormField(
        label=_("Text sent to order contact address"),
        required=False,
        widget=I18nMarkdownTextarea,
    )
    mail_send_download_reminder_attendee = forms.BooleanField(
        label=_("Send an email to attendees"),
        help_text=_('If the order contains attendees with email addresses different from the person who orders the '
                    'tickets, the following email will be sent out to the attendees.'),
        required=False,
    )
    mail_subject_download_reminder_attendee = I18nFormField(
        label=_("Subject sent to attendees"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_download_reminder_attendee = I18nFormField(
        label=_("Text sent to attendees"),
        required=False,
        widget=I18nMarkdownTextarea,
    )
    mail_days_download_reminder = forms.IntegerField(
        label=_("Number of days"),
        required=False,
        min_value=0,
        help_text=_("This email will be sent out this many days before the order event starts. If the "
                    "field is empty, the mail will never be sent.")
    )
    mail_subject_order_placed_require_approval = I18nFormField(
        label=_("Subject for received order"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_order_placed_require_approval = I18nFormField(
        label=_("Text for received order"),
        required=False,
        widget=I18nMarkdownTextarea,
    )
    mail_subject_order_approved = I18nFormField(
        label=_("Subject for approved order"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_order_approved = I18nFormField(
        label=_("Text for approved order"),
        required=False,
        widget=I18nMarkdownTextarea,
        help_text=_("This will only be sent out for non-free orders. Free orders will receive the free order "
                    "template from below instead."),
    )
    mail_send_order_approved_attendee = forms.BooleanField(
        label=_("Send an email to attendees"),
        help_text=_('If the order contains attendees with email addresses different from the person who orders the '
                    'tickets, the following email will be sent out to the attendees.'),
        required=False,
    )
    mail_subject_order_approved_attendee = I18nFormField(
        label=_("Subject sent to attendees"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_order_approved_attendee = I18nFormField(
        label=_("Text sent to attendees"),
        required=False,
        widget=I18nMarkdownTextarea,
        help_text=_("This will only be sent out for non-free orders. Free orders will receive the free order "
                    "template from below instead."),
    )
    mail_subject_order_approved_free = I18nFormField(
        label=_("Subject for approved free order"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_order_approved_free = I18nFormField(
        label=_("Text for approved free order"),
        required=False,
        widget=I18nMarkdownTextarea,
        help_text=_("This will only be sent out for free orders. Non-free orders will receive the non-free order "
                    "template from above instead."),
    )
    mail_send_order_approved_free_attendee = forms.BooleanField(
        label=_("Send an email to attendees"),
        help_text=_('If the order contains attendees with email addresses different from the person who orders the '
                    'tickets, the following email will be sent out to the attendees.'),
        required=False,
    )
    mail_subject_order_approved_free_attendee = I18nFormField(
        label=_("Subject sent to attendees"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_order_approved_free_attendee = I18nFormField(
        label=_("Text sent to attendees"),
        required=False,
        widget=I18nMarkdownTextarea,
        help_text=_("This will only be sent out for free orders. Non-free orders will receive the non-free order "
                    "template from above instead."),
    )
    mail_subject_order_denied = I18nFormField(
        label=_("Subject for denied order"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_order_denied = I18nFormField(
        label=_("Text for denied order"),
        required=False,
        widget=I18nMarkdownTextarea,
    )
    base_context = {
        'mail_text_order_placed': ['event', 'order', 'payments'],
        'mail_subject_order_placed': ['event', 'order', 'payments'],
        'mail_text_order_placed_attendee': ['event', 'order', 'position'],
        'mail_subject_order_placed_attendee': ['event', 'order', 'position'],
        'mail_text_order_placed_require_approval': ['event', 'order'],
        'mail_subject_order_placed_require_approval': ['event', 'order'],
        'mail_text_order_approved': ['event', 'order'],
        'mail_subject_order_approved': ['event', 'order'],
        'mail_text_order_approved_attendee': ['event', 'order', 'position'],
        'mail_subject_order_approved_attendee': ['event', 'order', 'position'],
        'mail_text_order_approved_free': ['event', 'order'],
        'mail_subject_order_approved_free': ['event', 'order'],
        'mail_text_order_approved_free_attendee': ['event', 'order', 'position'],
        'mail_subject_order_approved_free_attendee': ['event', 'order', 'position'],
        'mail_text_order_denied': ['event', 'order', 'comment'],
        'mail_subject_order_denied': ['event', 'order', 'comment'],
        'mail_text_order_paid': ['event', 'order', 'payment_info'],
        'mail_subject_order_paid': ['event', 'order', 'payment_info'],
        'mail_text_order_paid_attendee': ['event', 'order', 'position'],
        'mail_subject_order_paid_attendee': ['event', 'order', 'position'],
        'mail_text_order_free': ['event', 'order'],
        'mail_subject_order_free': ['event', 'order'],
        'mail_text_order_free_attendee': ['event', 'order', 'position'],
        'mail_subject_order_free_attendee': ['event', 'order', 'position'],
        'mail_text_order_changed': ['event', 'order'],
        'mail_subject_order_changed': ['event', 'order'],
        'mail_text_order_canceled': ['event', 'order', 'comment'],
        'mail_subject_order_canceled': ['event', 'order', 'comment'],
        'mail_text_order_expire_warning': ['event', 'order'],
        'mail_subject_order_expire_warning': ['event', 'order'],
        'mail_text_order_pending_warning': ['event', 'order'],
        'mail_subject_order_pending_warning': ['event', 'order'],
        'mail_text_order_incomplete_payment': ['event', 'order', 'pending_sum'],
        'mail_subject_order_incomplete_payment': ['event', 'order'],
        'mail_text_order_payment_failed': ['event', 'order'],
        'mail_subject_order_payment_failed': ['event', 'order'],
        'mail_text_order_custom_mail': ['event', 'order'],
        'mail_text_order_invoice': ['event', 'order', 'invoice'],
        'mail_subject_order_invoice': ['event', 'order', 'invoice'],
        'mail_text_download_reminder': ['event', 'order'],
        'mail_subject_download_reminder': ['event', 'order'],
        'mail_text_download_reminder_attendee': ['event', 'order', 'position'],
        'mail_subject_download_reminder_attendee': ['event', 'order', 'position'],
        'mail_text_resend_link': ['event', 'order'],
        'mail_subject_resend_link': ['event', 'order'],
        'mail_subject_resend_link_attendee': ['event', 'order', 'position'],
        'mail_text_waiting_list': ['event', 'waiting_list_entry', 'waiting_list_voucher'],
        'mail_subject_waiting_list': ['event', 'waiting_list_entry', 'waiting_list_voucher'],
        'mail_text_resend_all_links': ['event', 'orders'],
        'mail_subject_resend_all_links': ['event', 'orders'],
        'mail_attach_ical_description': ['event', 'event_or_subevent'],
    }
    plain_rendering = {
        'mail_text_order_invoice',
    }

    def __init__(self, *args, **kwargs):
        self.event = event = kwargs.get('obj')
        super().__init__(*args, **kwargs)
        self.fields['mail_html_renderer'].choices = [
            (r.identifier, r.verbose_name) for r in event.get_html_mail_renderers().values()
        ]
        self.fields['mail_sales_channel_placed_paid'].choices = (
            (c.identifier, c.label) for c in event.organizer.sales_channels.all()
        )
        self.fields['mail_sales_channel_download_reminder'].choices = (
            (c.identifier, c.label) for c in event.organizer.sales_channels.all()
        )

        prefetch_related_objects([self.event.organizer], Prefetch('meta_properties'))
        self.event.meta_values_cached = self.event.meta_values.select_related('property').all()

        for k, v in self.base_context.items():
            self._set_field_placeholders(k, v, rich=k.startswith('mail_text_') and k not in self.plain_rendering)

        for k, v in list(self.fields.items()):
            if k.endswith('_attendee') and not event.settings.attendee_emails_asked:
                # If we don't ask for attendee emails, we can't send them anything and we don't need to clutter
                # the user interface with it
                del self.fields[k]


class TicketSettingsForm(SettingsForm):
    auto_fields = [
        'ticket_download',
        'ticket_download_date',
        'ticket_download_addons',
        'ticket_download_nonadm',
        'ticket_download_pending',
        'ticket_download_require_validated_email',
        'ticket_secret_length',
    ]
    ticket_secret_generator = forms.ChoiceField(
        label=_("Ticket code generator"),
        help_text=_("For advanced users, usually does not need to be changed."),
        required=True,
        widget=forms.RadioSelect,
        choices=[]
    )

    def __init__(self, *args, **kwargs):
        event = kwargs.get('obj')
        super().__init__(*args, **kwargs)
        self.fields['ticket_secret_generator'].choices = [
            (r.identifier, r.verbose_name) for r in event.ticket_secret_generators.values()
        ]

    def prepare_fields(self):
        # See clean()
        for k, v in self.fields.items():
            v._required = v.required
            v.required = False
            v.widget.is_required = False
            if isinstance(v, I18nFormField):
                v._required = v.one_required
                v.one_required = False
                v.widget.enabled_locales = self.locales

    def clean(self):
        # required=True files should only be required if the feature is enabled
        cleaned_data = super().clean()
        enabled = cleaned_data.get('ticket_download') == 'True'
        if not enabled:
            return
        for k, v in self.fields.items():
            val = cleaned_data.get(k)
            if v._required and (val is None or val == ""):
                self.add_error(k, _('This field is required.'))


class CommentForm(I18nModelForm):

    def __init__(self, *args, **kwargs):
        self.readonly = kwargs.pop('readonly', None)
        super().__init__(*args, **kwargs)
        if self.readonly:
            self.fields['comment'].widget.attrs['readonly'] = 'readonly'

    class Meta:
        model = Event
        fields = ['comment']
        widgets = {
            'comment': forms.Textarea(attrs={
                'rows': 6,
                'class': 'helper-width-100',
            }),
        }


class CountriesAndEU(CachedCountries):
    override = {
        'ZZ': _('Any country'),
        'EU': _('European Union')
    }
    first = ['ZZ', 'EU']
    cache_subkey = 'with_any_or_eu'


class CountriesAndEUAndStates(CountriesAndEU):
    def __iter__(self):
        for country_code, country_name in super().__iter__():
            yield country_code, country_name
            if country_code in COUNTRIES_WITH_STATE_IN_ADDRESS and country_code not in {"IT"}:
                # Special case for Italy: Provinces are used in addresses, but are too low-level to
                # have influence on taxes, so we avoid the bloat in the list of selectable countries.
                types, form = COUNTRIES_WITH_STATE_IN_ADDRESS[country_code]
                yield from sorted(((state.code, country_name + " - " + state.name)
                                   for state in pycountry.subdivisions.get(country_code=country_code)
                                   if state.type in types), key=lambda s: s[1])


class TaxRuleLineForm(I18nForm):
    country = LazyTypedChoiceField(
        choices=CountriesAndEUAndStates(),
        required=False
    )
    address_type = forms.ChoiceField(
        choices=[
            ('', _('Any customer')),
            ('individual', _('Individual')),
            ('business', _('Business')),
            ('business_vat_id', _('Business with valid VAT ID')),
        ],
        required=False
    )
    action = forms.ChoiceField(
        choices=[
            ('vat', _('Charge VAT')),
            ('reverse', _('Reverse charge')),
            ('no', _('No VAT')),
            ('block', _('Sale not allowed')),
            ('require_approval', _('Order requires approval')),
        ],
    )
    code = forms.ChoiceField(
        label=_("Tax code"),
        choices=[("", _("Default tax code")), *TAX_CODE_LISTS],
        required=False,
    )
    rate = forms.DecimalField(
        label=_('Deviating tax rate'),
        max_digits=10, decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={
            'placeholder': _('Deviating tax rate'),
        })
    )
    invoice_text = I18nFormField(
        label=_('Text on invoice'),
        required=False,
        widget=I18nTextInput,
        widget_kwargs=dict(attrs={
            'placeholder': _('Text on invoice'),
        })
    )

    def __init__(self, *args, **kwargs):
        self.parent_form = kwargs.pop("parent_form")
        super().__init__(*args, **kwargs)

    def clean(self):
        d = super().clean()

        parent_code = self.parent_form.cleaned_data.get("code")
        parent_rate = self.parent_form.cleaned_data.get("rate")

        code = d.get("code") or parent_code
        rate = d.get("rate")
        if rate is None:
            rate = parent_rate

        if d.get("action") in ("reverse", "no", "block") and d.get("rate"):
            raise ValidationError(_("A combination of this calculation mode with a non-zero tax rate does not make sense."))

        if d.get("action") == "reverse" and d.get("code") and code != "AE":
            # Reverse charge but code is not reverse charge -- this is the one case we ignore if the "default code"
            # is used because it is the one scenario we can auto-fix
            raise ValidationError(_("This combination of calculation mode and tax code does not make sense."))

        if d.get("action") == "no" and code and code.split("/")[0] in ("S", "AE", "L", "M", "B"):
            # No VAT but code indicates VAT
            raise ValidationError(_("This combination of calculation mode and tax code does not make sense."))

        if d.get("action") == "vat" and code and rate != Decimal("0.00") and code.split("/")[0] in ("O", "E", "Z", "G", "K", "AE"):
            # VAT, but code indicates exempt
            raise ValidationError(_("A combination of this tax code with a non-zero tax rate does not make sense."))

        if d.get("action") == "vat" and code and rate == Decimal("0.00") and code.split("/")[0] in ("S", "L", "M", "B"):
            # no VAT, but code indicates non-exempt
            raise ValidationError(_("A combination of this tax code with a zero tax rate does not make sense."))

        return d


class I18nBaseFormSet(I18nFormSetMixin, forms.BaseFormSet):
    # compatibility shim for django-i18nfield library

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event', None)
        if self.event:
            kwargs['locales'] = self.event.settings.get('locales')
        super().__init__(*args, **kwargs)


class BaseTaxRuleLineFormSet(I18nBaseFormSet):

    def __init__(self, *args, **kwargs):
        self.parent_form = kwargs.pop('parent_form')
        super().__init__(*args, **kwargs)
        self.form_kwargs['parent_form'] = self.parent_form


TaxRuleLineFormSet = formset_factory(
    TaxRuleLineForm, formset=BaseTaxRuleLineFormSet,
    can_order=True, can_delete=True, extra=0
)


class TaxRuleForm(I18nModelForm):
    class Meta:
        model = TaxRule
        fields = [
            'name',
            'rate',
            'price_includes_tax',
            'code',
            'eu_reverse_charge',
            'home_country',
            'internal_name',
            'keep_gross_if_rate_changes'
        ]


class WidgetCodeForm(forms.Form):
    subevent = forms.ModelChoiceField(
        label=pgettext_lazy('subevent', "Date"),
        empty_label=pgettext_lazy('subevent', "All dates"),
        required=False,
        queryset=SubEvent.objects.none()
    )
    language = forms.ChoiceField(
        label=_("Language"),
        required=True,
        choices=settings.LANGUAGES
    )
    voucher = forms.CharField(
        label=_("Pre-selected voucher"),
        required=False,
        help_text=_("If set, the widget will show products as if this voucher has been entered and when a product is "
                    "bought via the widget, this voucher will be used. This can for example be used to provide "
                    "widgets that give discounts or unlock secret products.")
    )
    compatibility_mode = forms.BooleanField(
        label=_("Compatibility mode"),
        required=False,
        help_text=_("Our regular widget doesn't work in all website builders. If you run into trouble, try using "
                    "this compatibility mode.")
    )

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)

        if self.event.has_subevents:
            self.fields['subevent'].queryset = self.event.subevents.all()
        else:
            del self.fields['subevent']

        self.fields['language'].choices = [(l, n) for l, n in settings.LANGUAGES if l in self.event.settings.locales]

    def clean_voucher(self):
        v = self.cleaned_data.get('voucher')
        if not v:
            return

        if not self.event.vouchers.filter(code=v).exists():
            raise ValidationError(_('The given voucher code does not exist.'))

        return v


class EventDeleteForm(forms.Form):
    error_messages = {
        'slug_wrong': _("The slug you entered was not correct."),
    }
    slug = forms.CharField(
        max_length=255,
        label=_("Event slug"),
    )

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)

    def clean_slug(self):
        slug = self.cleaned_data.get('slug')
        if slug != self.event.slug:
            raise forms.ValidationError(
                self.error_messages['slug_wrong'],
                code='slug_wrong',
            )
        return slug


class QuickSetupForm(I18nForm):
    show_quota_left = forms.BooleanField(
        label=_("Show number of tickets left"),
        help_text=_("Publicly show how many tickets of a certain type are still available."),
        required=False
    )
    waiting_list_enabled = forms.BooleanField(
        label=_("Waiting list"),
        help_text=_("Once a ticket is sold out, people can add themselves to a waiting list. As soon as a ticket "
                    "becomes available again, it will be reserved for the first person on the waiting list and this "
                    "person will receive an email notification with a voucher that can be used to buy a ticket."),
        required=False
    )
    ticket_download = forms.BooleanField(
        label=_("Ticket downloads"),
        help_text=_("Your customers will be able to download their tickets in PDF format."),
        required=False
    )
    attendee_names_required = forms.BooleanField(
        label=_("Require all attendees to fill in their names"),
        help_text=_("By default, we will ask for names but not require them. You can turn this off completely in the "
                    "settings."),
        required=False
    )
    imprint_url = forms.URLField(
        label=_("Imprint URL"),
        help_text=_("This should point e.g. to a part of your website that has your contact details and legal "
                    "information."),
        required=False,
    )
    contact_mail = forms.EmailField(
        label=_("Contact address"),
        required=False,
        help_text=_("We'll show this publicly to allow attendees to contact you.")
    )
    total_quota = forms.IntegerField(
        label=_("Total capacity"),
        min_value=0,
        widget=forms.NumberInput(
            attrs={
                'placeholder': '∞'
            }
        ),
        required=False
    )
    payment_stripe__enabled = forms.BooleanField(
        label=_("Payment via Stripe"),
        help_text=_("Stripe is an online payments processor supporting credit cards and lots of other payment options. "
                    "To accept payments via Stripe, you will need to set up an account with them, which takes less "
                    "than five minutes using their simple interface."),
        required=False
    )
    payment_banktransfer__enabled = forms.BooleanField(
        label=_("Payment by bank transfer"),
        help_text=_("Your customers will be instructed to wire the money to your account. You can then import your "
                    "bank statements to process the payments within pretix, or mark them as paid manually."),
        required=False
    )
    btf = BankTransfer.form_fields()
    payment_banktransfer_bank_details_type = btf['bank_details_type']
    payment_banktransfer_bank_details_sepa_name = btf['bank_details_sepa_name']
    payment_banktransfer_bank_details_sepa_iban = btf['bank_details_sepa_iban']
    payment_banktransfer_bank_details_sepa_bic = btf['bank_details_sepa_bic']
    payment_banktransfer_bank_details_sepa_bank = btf['bank_details_sepa_bank']
    payment_banktransfer_bank_details = btf['bank_details']

    def __init__(self, *args, **kwargs):
        self.obj = kwargs.pop('event', None)
        self.locales = self.obj.settings.get('locales') if self.obj else kwargs.pop('locales', None)
        kwargs['locales'] = self.locales
        super().__init__(*args, **kwargs)
        if not self.obj.settings.payment_stripe_connect_client_id:
            del self.fields['payment_stripe__enabled']
        self.fields['payment_banktransfer_bank_details'].required = False
        for f in self.fields.values():
            if 'data-required-if' in f.widget.attrs:
                f.widget.attrs['data-required-if'] += ",#id_payment_banktransfer__enabled"

        self.fields['payment_banktransfer_bank_details'].widget.attrs["data-required-if"] = (
            "#id_payment_banktransfer_bank_details_type_1,#id_payment_banktransfer__enabled"
        )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('payment_banktransfer__enabled'):
            provider = BankTransfer(self.obj)
            cleaned_data = provider.settings_form_clean(cleaned_data)
        return cleaned_data


class QuickSetupProductForm(I18nForm):
    name = I18nFormField(
        max_length=200,  # Max length of Quota.name
        label=_("Product name"),
        widget=I18nTextInput
    )
    default_price = forms.DecimalField(
        label=_("Price (optional)"),
        max_digits=13, decimal_places=2, required=False,
        localize=True,
        widget=forms.TextInput(
            attrs={
                'placeholder': _('Free')
            }
        ),
    )
    quota = forms.IntegerField(
        label=_("Quantity available"),
        min_value=0,
        widget=forms.NumberInput(
            attrs={
                'placeholder': '∞'
            }
        ),
        initial=100,
        required=False
    )


class BaseQuickSetupProductFormSet(I18nFormSetMixin, forms.BaseFormSet):

    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event', None)
        if event:
            kwargs['locales'] = event.settings.get('locales')
        super().__init__(*args, **kwargs)


QuickSetupProductFormSet = formset_factory(
    QuickSetupProductForm,
    formset=BaseQuickSetupProductFormSet,
    can_order=False, can_delete=True, extra=0
)


class ItemMetaPropertyForm(forms.ModelForm):
    class Meta:
        fields = ['name', 'default', 'required', 'allowed_values']
        widgets = {
            'default': forms.TextInput()
        }


class ConfirmTextForm(I18nForm):
    text = I18nFormField(
        widget=I18nMarkdownTextarea,
        widget_kwargs={'attrs': {'rows': '2'}},
    )


class BaseConfirmTextFormSet(I18nFormSetMixin, forms.BaseFormSet):
    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event', None)
        if event:
            kwargs['locales'] = event.settings.get('locales')
        super().__init__(*args, **kwargs)


ConfirmTextFormset = formset_factory(
    ConfirmTextForm,
    formset=BaseConfirmTextFormSet,
    can_order=True, can_delete=True, extra=0
)


class EventFooterLinkForm(I18nModelForm):
    class Meta:
        model = EventFooterLink
        fields = ('label', 'url')
        widgets = {
            "url": forms.URLInput(
                attrs={
                    "placeholder": "https://..."
                }
            )
        }


class BaseEventFooterLinkFormSet(I18nFormSetMixin, forms.BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event', None)
        if event:
            kwargs['locales'] = event.settings.get('locales')
        super().__init__(*args, **kwargs)


EventFooterLinkFormset = inlineformset_factory(
    Event, EventFooterLink,
    EventFooterLinkForm,
    formset=BaseEventFooterLinkFormSet,
    can_order=False, can_delete=True, extra=0
)
