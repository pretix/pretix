#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
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
# This file contains Apache-licensed contributions copyrighted by: Bolutife Lawrence, Maico Timmerman
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from decimal import Decimal
from urllib.parse import urlparse

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.forms.utils import ErrorDict
from django.utils.crypto import get_random_string
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_scopes.forms import SafeModelMultipleChoiceField
from i18nfield.forms import I18nFormField, I18nTextarea
from phonenumber_field.formfields import PhoneNumberField
from pytz import common_timezones

from pretix.api.models import WebHook
from pretix.api.webhooks import get_all_webhook_events
from pretix.base.forms import I18nModelForm, PlaceholderValidator, SettingsForm
from pretix.base.forms.questions import (
    NamePartsFormField, WrappedPhoneNumberPrefixWidget, get_country_by_locale,
    get_phone_prefix,
)
from pretix.base.forms.widgets import SplitDateTimePickerWidget
from pretix.base.models import (
    Customer, Device, EventMetaProperty, Gate, GiftCard, Membership,
    MembershipType, Organizer, Team,
)
from pretix.base.settings import PERSON_NAME_SCHEMES, PERSON_NAME_TITLE_GROUPS
from pretix.control.forms import ExtFileField, SplitDateTimeField
from pretix.control.forms.event import (
    SafeEventMultipleChoiceField, multimail_validate,
)
from pretix.multidomain.models import KnownDomain
from pretix.multidomain.urlreverse import build_absolute_uri


class OrganizerForm(I18nModelForm):
    error_messages = {
        'duplicate_slug': _("This slug is already in use. Please choose a different one."),
    }

    class Meta:
        model = Organizer
        fields = ['name', 'slug']

    def clean_slug(self):
        slug = self.cleaned_data['slug']
        if Organizer.objects.filter(slug__iexact=slug).exists():
            raise forms.ValidationError(
                self.error_messages['duplicate_slug'],
                code='duplicate_slug',
            )
        return slug


class OrganizerDeleteForm(forms.Form):
    error_messages = {
        'slug_wrong': _("The slug you entered was not correct."),
    }
    slug = forms.CharField(
        max_length=255,
        label=_("Event slug"),
    )

    def __init__(self, *args, **kwargs):
        self.organizer = kwargs.pop('organizer')
        super().__init__(*args, **kwargs)

    def clean_slug(self):
        slug = self.cleaned_data.get('slug')
        if slug != self.organizer.slug:
            raise forms.ValidationError(
                self.error_messages['slug_wrong'],
                code='slug_wrong',
            )
        return slug


class OrganizerUpdateForm(OrganizerForm):

    def __init__(self, *args, **kwargs):
        self.domain = kwargs.pop('domain', False)
        self.change_slug = kwargs.pop('change_slug', False)
        kwargs.setdefault('initial', {})
        self.instance = kwargs['instance']
        if self.domain and self.instance:
            initial_domain = self.instance.domains.filter(event__isnull=True).first()
            if initial_domain:
                kwargs['initial'].setdefault('domain', initial_domain.domainname)

        super().__init__(*args, **kwargs)
        if not self.change_slug:
            self.fields['slug'].widget.attrs['readonly'] = 'readonly'
        if self.domain:
            self.fields['domain'] = forms.CharField(
                max_length=255,
                label=_('Custom domain'),
                required=False,
                help_text=_('You need to configure the custom domain in the webserver beforehand.')
            )

    def clean_domain(self):
        d = self.cleaned_data['domain']
        if d:
            if d == urlparse(settings.SITE_URL).hostname:
                raise ValidationError(
                    _('You cannot choose the base domain of this installation.')
                )
            if KnownDomain.objects.filter(domainname=d).exclude(organizer=self.instance.pk,
                                                                event__isnull=True).exists():
                raise ValidationError(
                    _('This domain is already in use for a different event or organizer.')
                )
        return d

    def clean_slug(self):
        if self.change_slug:
            return self.cleaned_data['slug']
        return self.instance.slug

    def save(self, commit=True):
        instance = super().save(commit)

        if self.domain:
            current_domain = instance.domains.first()
            if self.cleaned_data['domain']:
                if current_domain and current_domain.domainname != self.cleaned_data['domain']:
                    current_domain.delete()
                    KnownDomain.objects.create(organizer=instance, domainname=self.cleaned_data['domain'])
                elif not current_domain:
                    KnownDomain.objects.create(organizer=instance, domainname=self.cleaned_data['domain'])
            elif current_domain:
                current_domain.delete()
            instance.cache.clear()
            for ev in instance.events.all():
                ev.cache.clear()

        return instance


class EventMetaPropertyForm(forms.ModelForm):
    class Meta:
        model = EventMetaProperty
        fields = ['name', 'default', 'required', 'protected', 'allowed_values']
        widgets = {
            'default': forms.TextInput()
        }


class MembershipTypeForm(I18nModelForm):
    class Meta:
        model = MembershipType
        fields = ['name', 'transferable', 'allow_parallel_usage', 'max_usages']


class TeamForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        organizer = kwargs.pop('organizer')
        super().__init__(*args, **kwargs)
        self.fields['limit_events'].queryset = organizer.events.all().order_by(
            '-has_subevents', '-date_from'
        )

    class Meta:
        model = Team
        fields = ['name', 'all_events', 'limit_events', 'can_create_events',
                  'can_change_teams', 'can_change_organizer_settings',
                  'can_manage_gift_cards', 'can_manage_customers',
                  'can_change_event_settings', 'can_change_items',
                  'can_view_orders', 'can_change_orders', 'can_checkin_orders',
                  'can_view_vouchers', 'can_change_vouchers']
        widgets = {
            'limit_events': forms.CheckboxSelectMultiple(attrs={
                'data-inverse-dependency': '#id_all_events',
                'class': 'scrolling-multiple-choice scrolling-multiple-choice-large',
            }),
        }
        field_classes = {
            'limit_events': SafeEventMultipleChoiceField
        }

    def clean(self):
        data = super().clean()
        if self.instance.pk and not data['can_change_teams']:
            if not self.instance.organizer.teams.exclude(pk=self.instance.pk).filter(
                    can_change_teams=True, members__isnull=False
            ).exists():
                raise ValidationError(_('The changes could not be saved because there would be no remaining team with '
                                        'the permission to change teams and permissions.'))

        return data


class GateForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        kwargs.pop('organizer')
        super().__init__(*args, **kwargs)

    class Meta:
        model = Gate
        fields = ['name', 'identifier']


class DeviceForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        organizer = kwargs.pop('organizer')
        super().__init__(*args, **kwargs)
        self.fields['limit_events'].queryset = organizer.events.all().order_by(
            '-has_subevents', '-date_from'
        )
        self.fields['gate'].queryset = organizer.gates.all()

    def clean(self):
        d = super().clean()
        if not d['all_events'] and not d['limit_events']:
            raise ValidationError(_('Your device will not have access to anything, please select some events.'))

        return d

    class Meta:
        model = Device
        fields = ['name', 'all_events', 'limit_events', 'security_profile', 'gate']
        widgets = {
            'limit_events': forms.CheckboxSelectMultiple(attrs={
                'data-inverse-dependency': '#id_all_events',
                'class': 'scrolling-multiple-choice scrolling-multiple-choice-large',
            }),
        }
        field_classes = {
            'limit_events': SafeEventMultipleChoiceField
        }


class DeviceBulkEditForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        organizer = kwargs.pop('organizer')
        self.mixed_values = kwargs.pop('mixed_values')
        self.queryset = kwargs.pop('queryset')
        super().__init__(*args, **kwargs)
        self.fields['limit_events'].queryset = organizer.events.all().order_by(
            '-has_subevents', '-date_from'
        )
        self.fields['gate'].queryset = organizer.gates.all()

    def clean(self):
        d = super().clean()
        if self.prefix + '__events' in self.data.getlist('_bulk') and not d['all_events'] and not d['limit_events']:
            raise ValidationError(_('Your device will not have access to anything, please select some events.'))

        return d

    class Meta:
        model = Device
        fields = ['all_events', 'limit_events', 'security_profile', 'gate']
        widgets = {
            'limit_events': forms.CheckboxSelectMultiple(attrs={
                'data-inverse-dependency': '#id_all_events',
                'class': 'scrolling-multiple-choice scrolling-multiple-choice-large',
            }),
        }
        field_classes = {
            'limit_events': SafeEventMultipleChoiceField
        }

    def save(self, commit=True):
        objs = list(self.queryset)
        fields = set()

        check_map = {
            'all_events': '__events',
            'limit_events': '__events',
        }
        for k in self.fields:
            cb_val = self.prefix + check_map.get(k, k)
            if cb_val not in self.data.getlist('_bulk'):
                continue

            fields.add(k)
            for obj in objs:
                if k == 'limit_events':
                    getattr(obj, k).set(self.cleaned_data[k])
                else:
                    setattr(obj, k, self.cleaned_data[k])

        if fields:
            Device.objects.bulk_update(objs, [f for f in fields if f != 'limit_events'], 200)

    def full_clean(self):
        if len(self.data) == 0:
            # form wasn't submitted
            self._errors = ErrorDict()
            return
        super().full_clean()


class OrganizerSettingsForm(SettingsForm):
    timezone = forms.ChoiceField(
        choices=((a, a) for a in common_timezones),
        label=_("Default timezone"),
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
        'allowed_restricted_plugins',
        'customer_accounts',
        'customer_accounts_link_by_email',
        'invoice_regenerate_allowed',
        'contact_mail',
        'imprint_url',
        'organizer_info_text',
        'event_list_type',
        'event_list_availability',
        'organizer_homepage_text',
        'organizer_link_back',
        'organizer_logo_image_large',
        'organizer_logo_image_inherit',
        'giftcard_length',
        'giftcard_expiry_years',
        'locales',
        'region',
        'meta_noindex',
        'event_team_provisioning',
        'primary_color',
        'theme_color_success',
        'theme_color_danger',
        'theme_color_background',
        'theme_round_borders',
        'primary_font',
        'privacy_url',
        'cookie_consent',
        'cookie_consent_dialog_title',
        'cookie_consent_dialog_text',
        'cookie_consent_dialog_text_secondary',
        'cookie_consent_dialog_button_yes',
        'cookie_consent_dialog_button_no',
    ]

    organizer_logo_image = ExtFileField(
        label=_('Header image'),
        ext_whitelist=(".png", ".jpg", ".gif", ".jpeg"),
        max_size=settings.FILE_UPLOAD_MAX_SIZE_IMAGE,
        required=False,
        help_text=_('If you provide a logo image, we will by default not show your organization name '
                    'in the page header. By default, we show your logo with a size of up to 1140x120 pixels. You '
                    'can increase the size with the setting below. We recommend not using small details on the picture '
                    'as it will be resized on smaller screens.')
    )
    favicon = ExtFileField(
        label=_('Favicon'),
        ext_whitelist=(".ico", ".png", ".jpg", ".gif", ".jpeg"),
        required=False,
        max_size=settings.FILE_UPLOAD_MAX_SIZE_FAVICON,
        help_text=_('If you provide a favicon, we will show it instead of the default pretix icon. '
                    'We recommend a size of at least 200x200px to accommodate most devices.')
    )

    def __init__(self, *args, **kwargs):
        is_admin = kwargs.pop('is_admin', False)
        super().__init__(*args, **kwargs)

        if not is_admin:
            del self.fields['allowed_restricted_plugins']

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
            ))
            for k, v in PERSON_NAME_TITLE_GROUPS.items()
        ]


class MailSettingsForm(SettingsForm):
    auto_fields = [
        'mail_from_name',
    ]

    mail_bcc = forms.CharField(
        label=_("Bcc address"),
        help_text=_("All emails will be sent to this address as a Bcc copy"),
        validators=[multimail_validate],
        required=False,
        max_length=255
    )
    mail_text_signature = I18nFormField(
        label=_("Signature"),
        required=False,
        widget=I18nTextarea,
        help_text=_("This will be attached to every email."),
        validators=[PlaceholderValidator([])],
        widget_kwargs={'attrs': {
            'rows': '4',
            'placeholder': _(
                'e.g. your contact details'
            )
        }}
    )

    mail_text_customer_registration = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nTextarea,
    )
    mail_text_customer_email_change = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nTextarea,
    )
    mail_text_customer_reset = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nTextarea,
    )

    base_context = {
        'mail_text_customer_registration': ['customer', 'url'],
        'mail_text_customer_email_change': ['customer', 'url'],
        'mail_text_customer_reset': ['customer', 'url'],
    }

    def _get_sample_context(self, base_parameters):
        placeholders = {
            'organizer': self.organizer.name
        }

        if 'url' in base_parameters:
            placeholders['url'] = build_absolute_uri(
                self.organizer,
                'presale:organizer.customer.activate'
            ) + '?token=' + get_random_string(30)

        if 'customer' in base_parameters:
            placeholders['name'] = pgettext_lazy('person_name_sample', 'John Doe')
            name_scheme = PERSON_NAME_SCHEMES[self.organizer.settings.name_scheme]
            for f, l, w in name_scheme['fields']:
                if f == 'full_name':
                    continue
                placeholders['name_%s' % f] = name_scheme['sample'][f]
            placeholders['name_for_salutation'] = _("Mr Doe")
        return placeholders

    def _set_field_placeholders(self, fn, base_parameters):
        phs = [
            '{%s}' % p
            for p in sorted(self._get_sample_context(base_parameters).keys())
        ]
        ht = _('Available placeholders: {list}').format(
            list=', '.join(phs)
        )
        if self.fields[fn].help_text:
            self.fields[fn].help_text += ' ' + str(ht)
        else:
            self.fields[fn].help_text = ht
        self.fields[fn].validators.append(
            PlaceholderValidator(phs)
        )

    def __init__(self, *args, **kwargs):
        self.organizer = kwargs.get('obj')
        super().__init__(*args, **kwargs)
        for k, v in self.base_context.items():
            self._set_field_placeholders(k, v)


class WebHookForm(forms.ModelForm):
    events = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple,
        label=pgettext_lazy('webhooks', 'Event types')
    )

    def __init__(self, *args, **kwargs):
        organizer = kwargs.pop('organizer')
        super().__init__(*args, **kwargs)
        self.fields['limit_events'].queryset = organizer.events.all()
        self.fields['events'].choices = [
            (
                a.action_type,
                mark_safe('{} – <code>{}</code>'.format(a.verbose_name, a.action_type))
            ) for a in get_all_webhook_events().values()
        ]
        if self.instance:
            self.fields['events'].initial = list(self.instance.listeners.values_list('action_type', flat=True))

    class Meta:
        model = WebHook
        fields = ['target_url', 'enabled', 'all_events', 'limit_events']
        widgets = {
            'limit_events': forms.CheckboxSelectMultiple(attrs={
                'data-inverse-dependency': '#id_all_events'
            }),
        }
        field_classes = {
            'limit_events': SafeModelMultipleChoiceField
        }


class GiftCardCreateForm(forms.ModelForm):
    value = forms.DecimalField(
        label=_('Gift card value'),
        min_value=Decimal('0.00')
    )

    def __init__(self, *args, **kwargs):
        self.organizer = kwargs.pop('organizer')
        initial = kwargs.pop('initial', {})
        initial['expires'] = self.organizer.default_gift_card_expiry
        kwargs['initial'] = initial
        super().__init__(*args, **kwargs)

    def clean_secret(self):
        s = self.cleaned_data['secret']
        if GiftCard.objects.filter(
                secret__iexact=s
        ).filter(
            Q(issuer=self.organizer) | Q(issuer__gift_card_collector_acceptance__collector=self.organizer)
        ).exists():
            raise ValidationError(
                _('A gift card with the same secret already exists in your or an affiliated organizer account.')
            )
        return s

    class Meta:
        model = GiftCard
        fields = ['secret', 'currency', 'testmode', 'expires', 'conditions']
        field_classes = {
            'expires': SplitDateTimeField
        }
        widgets = {
            'expires': SplitDateTimePickerWidget,
            'conditions': forms.Textarea(attrs={"rows": 2})
        }


class GiftCardUpdateForm(forms.ModelForm):
    class Meta:
        model = GiftCard
        fields = ['expires', 'conditions']
        field_classes = {
            'expires': SplitDateTimeField
        }
        widgets = {
            'expires': SplitDateTimePickerWidget,
            'conditions': forms.Textarea(attrs={"rows": 2})
        }


class CustomerUpdateForm(forms.ModelForm):
    error_messages = {
        'duplicate': _("An account with this email address is already registered."),
    }

    class Meta:
        model = Customer
        fields = ['is_active', 'external_identifier', 'name_parts', 'email', 'is_verified', 'phone', 'locale', 'notes']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.phone and (self.instance.organizer.settings.region or self.instance.locale):
            country_code = self.instance.organizer.settings.region or get_country_by_locale(self.instance.locale)
            phone_prefix = get_phone_prefix(country_code)
            if phone_prefix:
                self.initial['phone'] = "+{}.".format(phone_prefix)

        self.fields['phone'] = PhoneNumberField(
            label=_('Phone'),
            required=False,
            widget=WrappedPhoneNumberPrefixWidget()
        )
        self.fields['name_parts'] = NamePartsFormField(
            max_length=255,
            required=False,
            scheme=self.instance.organizer.settings.name_scheme,
            titles=self.instance.organizer.settings.name_scheme_titles,
            label=_('Name'),
        )

    def clean(self):
        email = self.cleaned_data.get('email')

        if email is not None:
            try:
                self.instance.organizer.customers.exclude(pk=self.instance.pk).get(email=email)
            except Customer.DoesNotExist:
                pass
            else:
                raise forms.ValidationError(
                    self.error_messages['duplicate'],
                    code='duplicate',
                )

        return self.cleaned_data


class CustomerCreateForm(CustomerUpdateForm):

    class Meta:
        model = Customer
        fields = ['is_active', 'identifier', 'external_identifier', 'name_parts', 'email', 'is_verified', 'phone', 'locale', 'notes']


class MembershipUpdateForm(forms.ModelForm):

    class Meta:
        model = Membership
        fields = ['testmode', 'membership_type', 'date_start', 'date_end', 'attendee_name_parts', 'canceled']
        field_classes = {
            'date_start': SplitDateTimeField,
            'date_end': SplitDateTimeField,
        }
        widgets = {
            'date_start': SplitDateTimePickerWidget(),
            'date_end': SplitDateTimePickerWidget(attrs={'data-date-after': '#id_date_Start'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            del self.fields['testmode']

        self.fields['membership_type'].queryset = self.instance.customer.organizer.membership_types.all()
        self.fields['attendee_name_parts'] = NamePartsFormField(
            max_length=255,
            required=False,
            scheme=self.instance.customer.organizer.settings.name_scheme,
            titles=self.instance.customer.organizer.settings.name_scheme_titles,
            label=_('Attendee name'),
        )
