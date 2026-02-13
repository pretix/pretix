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
from django.forms import formset_factory, inlineformset_factory
from django.forms.utils import ErrorDict
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils.html import conditional_escape, format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_scopes.forms import SafeModelChoiceField
from i18nfield.forms import (
    I18nForm, I18nFormField, I18nFormSetMixin, I18nTextInput,
)
from i18nfield.strings import LazyI18nString
from phonenumber_field.formfields import PhoneNumberField
from pytz import common_timezones

from pretix.api.auth.devicesecurity import get_all_security_profiles
from pretix.api.models import WebHook
from pretix.api.webhooks import get_all_webhook_events
from pretix.base.customersso.oidc import oidc_validate_and_complete_config
from pretix.base.forms import (
    SECRET_REDACTED, I18nMarkdownTextarea, I18nModelForm, PlaceholderValidator,
    SecretKeySettingsField, SettingsForm,
)
from pretix.base.forms.questions import (
    NamePartsFormField, WrappedPhoneNumberPrefixWidget, get_country_by_locale,
    get_phone_prefix,
)
from pretix.base.forms.widgets import (
    SplitDateTimePickerWidget, format_placeholders_help_text,
)
from pretix.base.models import (
    Customer, Device, Event, EventMetaProperty, Gate, GiftCard,
    GiftCardAcceptance, Membership, MembershipType, OrderPosition, Organizer,
    ReusableMedium, SalesChannel, Team,
)
from pretix.base.models.customers import CustomerSSOClient, CustomerSSOProvider
from pretix.base.models.organizer import OrganizerFooterLink
from pretix.base.settings import (
    PERSON_NAME_SCHEMES, PERSON_NAME_TITLE_GROUPS, validate_organizer_settings,
)
from pretix.control.forms import ExtFileField, SplitDateTimeField
from pretix.control.forms.event import (
    SafeEventMultipleChoiceField, multimail_validate,
)
from pretix.control.forms.widgets import Select2
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
        self.change_slug = kwargs.pop('change_slug', False)
        kwargs.setdefault('initial', {})
        self.instance = kwargs['instance']

        super().__init__(*args, **kwargs)
        if not self.change_slug:
            self.fields['slug'].widget.attrs['readonly'] = 'readonly'

    def clean_slug(self):
        if self.change_slug:
            return self.cleaned_data['slug']
        return self.instance.slug


class KnownDomainForm(forms.ModelForm):
    class Meta:
        model = KnownDomain
        fields = ["domainname", "mode", "event"]
        field_classes = {
            "event": SafeModelChoiceField,
        }

    def __init__(self, *args, **kwargs):
        self.organizer = kwargs.pop('organizer')
        super().__init__(*args, **kwargs)
        self.fields["event"].queryset = self.organizer.events.all()
        if self.instance and self.instance.pk:
            self.fields["domainname"].widget.attrs['readonly'] = 'readonly'

    def clean_domainname(self):
        if self.instance and self.instance.pk:
            return self.instance.domainname
        d = self.cleaned_data['domainname']
        if d:
            if d == urlparse(settings.SITE_URL).hostname:
                raise ValidationError(
                    _('You cannot choose the base domain of this installation.')
                )
            if KnownDomain.objects.filter(domainname=d).exclude(organizer=self.instance.organizer).exists():
                raise ValidationError(
                    _('This domain is already in use for a different event or organizer.')
                )
        return d

    def clean(self):
        d = super().clean()

        if d["mode"] == KnownDomain.MODE_ORG_DOMAIN and d["event"]:
            raise ValidationError(
                _("Do not choose an event for this mode.")
            )

        if d["mode"] == KnownDomain.MODE_ORG_ALT_DOMAIN and d["event"]:
            raise ValidationError(
                _("Do not choose an event for this mode. You can assign events to this domain in event settings.")
            )

        if d["mode"] == KnownDomain.MODE_EVENT_DOMAIN and not d["event"]:
            raise ValidationError(
                _("You need to choose an event.")
            )

        return d


class BaseKnownDomainFormSet(forms.BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        self.organizer = kwargs.pop('organizer')
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        kwargs['organizer'] = self.organizer
        return super()._construct_form(i, **kwargs)

    @property
    def empty_form(self):
        form = self.form(
            auto_id=self.auto_id,
            prefix=self.add_prefix('__prefix__'),
            empty_permitted=True,
            use_required_attribute=False,
            organizer=self.organizer,
        )
        self.add_fields(form, None)
        return form

    def clean(self):
        super().clean()
        data = [f.cleaned_data for f in self.forms]

        if len([d for d in data if d.get("mode") == KnownDomain.MODE_ORG_DOMAIN and not d.get("DELETE")]) > 1:
            raise ValidationError(_("You may set only one organizer domain."))

        return data


KnownDomainFormset = inlineformset_factory(
    Organizer, KnownDomain,
    KnownDomainForm,
    formset=BaseKnownDomainFormSet,
    can_order=False, can_delete=True, extra=0
)


class SafeOrderPositionChoiceField(forms.ModelChoiceField):
    def __init__(self, queryset, **kwargs):
        queryset = queryset.model.all.none()
        super().__init__(queryset, **kwargs)

    def label_from_instance(self, op):
        return f'{op.order.code}-{op.positionid} ({str(op.item) + ((" - " + str(op.variation)) if op.variation else "")})'


class EventMetaPropertyForm(I18nModelForm):
    class Meta:
        model = EventMetaProperty
        fields = ['name', 'default', 'required', 'protected', 'filter_public', 'public_label', 'filter_allowed']
        widgets = {
            'default': forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['public_label'].widget.attrs['data-display-dependency'] = '#id_filter_public'


class EventMetaPropertyAllowedValueForm(I18nForm):
    key = forms.CharField(
        label=_('Internal name'),
        max_length=250,
        required=True
    )
    label = I18nFormField(
        label=_('Public name'),
        required=False,
        widget=I18nTextInput,
        widget_kwargs=dict(attrs={
            'placeholder': _('Public name'),
        })
    )


class I18nBaseFormSet(I18nFormSetMixin, forms.BaseFormSet):
    # compatibility shim for django-i18nfield library

    def __init__(self, *args, **kwargs):
        self.organizer = kwargs.pop('organizer', None)
        if self.organizer:
            kwargs['locales'] = self.organizer.settings.get('locales')
        super().__init__(*args, **kwargs)


EventMetaPropertyAllowedValueFormSet = formset_factory(
    EventMetaPropertyAllowedValueForm, formset=I18nBaseFormSet,
    can_order=True, can_delete=True, extra=0
)


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
        fields = ['name', 'require_2fa', 'all_events', 'limit_events', 'can_create_events',
                  'can_change_teams', 'can_change_organizer_settings',
                  'can_manage_gift_cards', 'can_manage_customers',
                  'can_manage_reusable_media',
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
        self.fields['security_profile'] = forms.ChoiceField(
            label=self.fields['security_profile'].label,
            help_text=self.fields['security_profile'].help_text,
            choices=[(k, v.verbose_name) for k, v in get_all_security_profiles().items()],
        )

    def clean(self):
        d = super().clean()
        if not d['all_events'] and not d.get('limit_events'):
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
        self.fields['security_profile'] = forms.ChoiceField(
            label=self.fields['security_profile'].label,
            help_text=self.fields['security_profile'].help_text,
            choices=[(k, v.verbose_name) for k, v in get_all_security_profiles().items()],
        )

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
        'customer_accounts_native',
        'customer_accounts_link_by_email',
        'customer_accounts_require_login_for_order_access',
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
        'favicon',
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
        'accessibility_url',
        'accessibility_title',
        'accessibility_text',
        'cookie_consent',
        'cookie_consent_dialog_title',
        'cookie_consent_dialog_text',
        'cookie_consent_dialog_text_secondary',
        'cookie_consent_dialog_button_yes',
        'cookie_consent_dialog_button_no',
        'reusable_media_active',
        'reusable_media_type_barcode',
        'reusable_media_type_barcode_identifier_length',
        'reusable_media_type_nfc_uid',
        'reusable_media_type_nfc_uid_autocreate_giftcard',
        'reusable_media_type_nfc_uid_autocreate_giftcard_currency',
        'reusable_media_type_nfc_mf0aes',
        'reusable_media_type_nfc_mf0aes_autocreate_giftcard',
        'reusable_media_type_nfc_mf0aes_autocreate_giftcard_currency',
        'reusable_media_type_nfc_mf0aes_random_uid',
    ]

    organizer_logo_image = ExtFileField(
        label=_('Header image'),
        ext_whitelist=settings.FILE_UPLOAD_EXTENSIONS_IMAGE,
        max_size=settings.FILE_UPLOAD_MAX_SIZE_IMAGE,
        required=False,
        help_text=_('If you provide a logo image, we will by default not show your organization name '
                    'in the page header. If you use a white background, we show your logo with a size of up '
                    'to 1140x120 pixels. Otherwise the maximum size is 1120x120 pixels. You '
                    'can increase the size with the setting below. We recommend not using small details on the picture '
                    'as it will be resized on smaller screens.')
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
        self.fields['reusable_media_active'].label = mark_safe(
            conditional_escape(self.fields['reusable_media_active'].label) +
            ' ' +
            '<span class="label label-info">{}</span>'.format(_('experimental'))
        )
        self.fields['reusable_media_active'].help_text = mark_safe(
            conditional_escape(self.fields['reusable_media_active'].help_text) +
            ' ' +
            '<br/><span class="fa fa-flask"></span> ' +
            _('This feature is currently in an experimental stage. It only supports very limited use cases and might '
              'change at any point.')
        )

    def clean(self):
        data = super().clean()
        settings_dict = self.obj.settings.freeze()
        settings_dict.update(data)

        validate_organizer_settings(self.obj, data)
        return data


class MailSettingsForm(SettingsForm):
    auto_fields = [
        'mail_from_name',
    ]

    mail_bcc = forms.CharField(
        label=_("Bcc address"),
        help_text=''.join([
            str(_("All emails will be sent to this address as a Bcc copy.")),
            str(_("You can specify multiple recipients separated by commas.")),
            str(_("Sensitive emails like password resets will not be sent in Bcc.")),
        ]),
        validators=[multimail_validate],
        required=False,
        max_length=255
    )
    mail_text_signature = I18nFormField(
        label=_("Signature"),
        required=False,
        widget=I18nMarkdownTextarea,
        help_text=_("This will be attached to every email."),
        validators=[PlaceholderValidator([])],
        widget_kwargs={'attrs': {
            'rows': '4',
            'placeholder': _(
                'e.g. your contact details'
            )
        }}
    )

    mail_subject_customer_registration = I18nFormField(
        label=_("Subject"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_customer_registration = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nMarkdownTextarea,
    )
    mail_subject_customer_email_change = I18nFormField(
        label=_("Subject"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_customer_email_change = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nMarkdownTextarea,
    )
    mail_subject_customer_reset = I18nFormField(
        label=_("Subject"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_customer_reset = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nMarkdownTextarea,
    )
    mail_subject_customer_security_notice = I18nFormField(
        label=_("Subject"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_customer_security_notice = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nMarkdownTextarea,
    )

    base_context = {
        'mail_text_customer_registration': ['customer', 'url'],
        'mail_subject_customer_registration': ['customer', 'url'],
        'mail_text_customer_email_change': ['customer', 'url'],
        'mail_subject_customer_email_change': ['customer', 'url'],
        'mail_text_customer_reset': ['customer', 'url'],
        'mail_subject_customer_reset': ['customer', 'url'],
        'mail_text_customer_security_notice': ['customer', 'url', 'message'],
        'mail_subject_customer_security_notice': ['customer', 'url', 'message'],
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

        if 'message' in base_parameters:
            placeholders['message'] = _('Your password has been changed.')

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
        placeholders = self._get_sample_context(base_parameters)
        ht = format_placeholders_help_text(placeholders)
        if self.fields[fn].help_text:
            self.fields[fn].help_text += ' ' + str(ht)
        else:
            self.fields[fn].help_text = ht
        self.fields[fn].validators.append(
            PlaceholderValidator(['{%s}' % p for p in placeholders.keys()])
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
                format_html('{} – <code>{}</code><br><span class="text-muted">{}</span>', a.verbose_name, a.action_type, a.help_text)
                if a.help_text else
                format_html('{} – <code>{}</code>', a.verbose_name, a.action_type)
            ) for a in get_all_webhook_events().values()
        ]
        if self.instance and self.instance.pk:
            self.fields['events'].initial = list(self.instance.listeners.values_list('action_type', flat=True))

    class Meta:
        model = WebHook
        fields = ['target_url', 'enabled', 'all_events', 'limit_events', 'comment']
        widgets = {
            'limit_events': forms.CheckboxSelectMultiple(attrs={
                'data-inverse-dependency': '#id_all_events',
                'class': 'scrolling-multiple-choice scrolling-multiple-choice-large',
            }),
        }
        field_classes = {
            'limit_events': SafeEventMultipleChoiceField
        }


class GiftCardCreateForm(forms.ModelForm):
    value = forms.DecimalField(
        label=_('Gift card value'),
        min_value=Decimal('0.00'),
        max_value=Decimal('99999999.99'),
    )

    def __init__(self, *args, **kwargs):
        self.organizer = kwargs.pop('organizer')
        initial = kwargs.pop('initial', {})
        initial['expires'] = self.organizer.default_gift_card_expiry
        kwargs['initial'] = initial
        super().__init__(*args, **kwargs)

        if self.organizer.settings.customer_accounts:
            self.fields['customer'].queryset = self.organizer.customers.all()
            self.fields['customer'].widget = Select2(
                attrs={
                    'data-model-select2': 'generic',
                    'data-select2-url': reverse('control:organizer.customers.select2', kwargs={
                        'organizer': self.organizer.slug,
                    }),
                }
            )
            self.fields['customer'].widget.choices = self.fields['customer'].choices
            self.fields['customer'].required = False
        else:
            del self.fields['customer']

    def clean_secret(self):
        s = self.cleaned_data['secret']
        if GiftCard.objects.filter(
                secret__iexact=s
        ).filter(
            Q(issuer=self.organizer) |
            Q(issuer__in=GiftCardAcceptance.objects.filter(
                acceptor=self.organizer,
                active=True,
            ).values_list('issuer', flat=True))
        ).exists():
            raise ValidationError(
                _('A gift card with the same secret already exists in your or an affiliated organizer account.')
            )
        return s

    class Meta:
        model = GiftCard
        fields = ['secret', 'currency', 'testmode', 'expires', 'conditions', 'customer']
        field_classes = {
            'expires': SplitDateTimeField,
            'customer': SafeModelChoiceField,
        }
        widgets = {
            'expires': SplitDateTimePickerWidget,
            'conditions': forms.Textarea(attrs={"rows": 2})
        }


class GiftCardUpdateForm(forms.ModelForm):
    class Meta:
        model = GiftCard
        fields = ['expires', 'conditions', 'owner_ticket', 'customer']
        field_classes = {
            'expires': SplitDateTimeField,
            'owner_ticket': SafeOrderPositionChoiceField,
            'customer': SafeModelChoiceField,
        }
        widgets = {
            'expires': SplitDateTimePickerWidget,
            'conditions': forms.Textarea(attrs={"rows": 2})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        organizer = self.instance.issuer

        self.fields['owner_ticket'].queryset = OrderPosition.all.filter(order__event__organizer=organizer).all()
        self.fields['owner_ticket'].widget = Select2(
            attrs={
                'data-model-select2': 'generic',
                'data-select2-url': reverse('control:organizer.ticket_select2', kwargs={
                    'organizer': organizer.slug,
                }),
            }
        )
        self.fields['owner_ticket'].widget.choices = self.fields['owner_ticket'].choices
        self.fields['owner_ticket'].required = False

        if organizer.settings.customer_accounts:
            self.fields['customer'].queryset = organizer.customers.all()
            self.fields['customer'].widget = Select2(
                attrs={
                    'data-model-select2': 'generic',
                    'data-select2-url': reverse('control:organizer.customers.select2', kwargs={
                        'organizer': organizer.slug,
                    }),
                }
            )
            self.fields['customer'].widget.choices = self.fields['customer'].choices
            self.fields['customer'].required = False
        else:
            del self.fields['customer']


class ReusableMediumUpdateForm(forms.ModelForm):
    error_messages = {
        'duplicate': _("An medium with this type and identifier is already registered."),
    }

    class Meta:
        model = ReusableMedium
        fields = ['active', 'expires', 'customer', 'linked_giftcard', 'linked_orderposition', 'notes']
        field_classes = {
            'expires': SplitDateTimeField,
            'customer': SafeModelChoiceField,
            'linked_giftcard': SafeModelChoiceField,
            'linked_orderposition': SafeOrderPositionChoiceField,
        }
        widgets = {
            'expires': SplitDateTimePickerWidget,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        organizer = self.instance.organizer

        self.fields['linked_orderposition'].queryset = OrderPosition.all.filter(order__event__organizer=organizer).all()
        self.fields['linked_orderposition'].widget = Select2(
            attrs={
                'data-model-select2': 'generic',
                'data-select2-url': reverse('control:organizer.ticket_select2', kwargs={
                    'organizer': organizer.slug,
                }),
            }
        )
        self.fields['linked_orderposition'].widget.choices = self.fields['linked_orderposition'].choices
        self.fields['linked_orderposition'].required = False

        self.fields['linked_giftcard'].queryset = organizer.issued_gift_cards.all()
        self.fields['linked_giftcard'].widget = Select2(
            attrs={
                'data-model-select2': 'generic',
                'data-select2-url': reverse('control:organizer.giftcards.select2', kwargs={
                    'organizer': organizer.slug,
                }),
            }
        )
        self.fields['linked_giftcard'].widget.choices = self.fields['linked_giftcard'].choices
        self.fields['linked_giftcard'].required = False

        if organizer.settings.customer_accounts:
            self.fields['customer'].queryset = organizer.customers.all()
            self.fields['customer'].widget = Select2(
                attrs={
                    'data-model-select2': 'generic',
                    'data-select2-url': reverse('control:organizer.customers.select2', kwargs={
                        'organizer': organizer.slug,
                    }),
                }
            )
            self.fields['customer'].widget.choices = self.fields['customer'].choices
            self.fields['customer'].required = False
        else:
            del self.fields['customer']

    def clean(self):
        identifier = self.cleaned_data.get('identifier')
        type = self.cleaned_data.get('type')

        if identifier is not None and type is not None:
            try:
                self.instance.organizer.reusable_media.exclude(pk=self.instance.pk).get(
                    identifier=identifier,
                    type=type,
                )
            except ReusableMedium.DoesNotExist:
                pass
            else:
                raise forms.ValidationError(
                    self.error_messages['duplicate'],
                    code='duplicate',
                )

        return self.cleaned_data


class ReusableMediumCreateForm(ReusableMediumUpdateForm):

    class Meta:
        model = ReusableMedium
        fields = ['active', 'type', 'identifier', 'expires', 'linked_orderposition', 'linked_giftcard', 'customer', 'notes']
        field_classes = {
            'expires': SplitDateTimeField,
            'customer': SafeModelChoiceField,
            'linked_giftcard': SafeModelChoiceField,
            'linked_orderposition': SafeOrderPositionChoiceField,
        }
        widgets = {
            'expires': SplitDateTimePickerWidget,
        }


class CustomerUpdateForm(forms.ModelForm):
    error_messages = {
        'duplicate_identifier': _("An account with this customer ID is already registered."),
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
        if self.instance.provider_id:
            self.fields['email'].disabled = True
            self.fields['is_verified'].disabled = True
            self.fields['external_identifier'].disabled = True

    def clean(self):
        email = self.cleaned_data.get('email')
        identifier = self.cleaned_data.get('identifier')

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

        if identifier is not None:
            try:
                self.instance.organizer.customers.exclude(pk=self.instance.pk).get(identifier=identifier)
            except Customer.DoesNotExist:
                pass
            else:
                raise forms.ValidationError(
                    self.error_messages['duplicate_identifier'],
                    code='duplicate_identifier',
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


class OrganizerFooterLinkForm(I18nModelForm):
    class Meta:
        model = OrganizerFooterLink
        fields = ('label', 'url')
        widgets = {
            "url": forms.URLInput(
                attrs={
                    "placeholder": "https://..."
                }
            )
        }


class BaseOrganizerFooterLinkFormSet(I18nFormSetMixin, forms.BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        organizer = kwargs.pop('organizer', None)
        if organizer:
            kwargs['locales'] = organizer.settings.get('locales')
        super().__init__(*args, **kwargs)


OrganizerFooterLinkFormset = inlineformset_factory(
    Organizer, OrganizerFooterLink,
    OrganizerFooterLinkForm,
    formset=BaseOrganizerFooterLinkFormSet,
    can_order=False, can_delete=True, extra=0
)


class SSOProviderForm(I18nModelForm):

    config_oidc_base_url = forms.URLField(
        label=pgettext_lazy('sso_oidc', 'Base URL'),
        required=False,
    )
    config_oidc_client_id = forms.CharField(
        label=pgettext_lazy('sso_oidc', 'Client ID'),
        required=False,
    )
    config_oidc_client_secret = SecretKeySettingsField(
        label=pgettext_lazy('sso_oidc', 'Client secret'),
        required=False,
    )
    config_oidc_scope = forms.CharField(
        label=pgettext_lazy('sso_oidc', 'Scope'),
        help_text=pgettext_lazy('sso_oidc', 'Multiple scopes separated with spaces.'),
        required=False,
    )
    config_oidc_uid_field = forms.CharField(
        label=pgettext_lazy('sso_oidc', 'User ID field'),
        help_text=pgettext_lazy('sso_oidc', 'We will assume that the contents of the user ID fields are unique and '
                                            'can never change for a user.'),
        required=True,
        initial='sub',
    )
    config_oidc_email_field = forms.CharField(
        label=pgettext_lazy('sso_oidc', 'Email field'),
        help_text=pgettext_lazy('sso_oidc', 'We will assume that all email addresses received from the SSO provider '
                                            'are verified to really belong the the user. If this can\'t be '
                                            'guaranteed, security issues might arise.'),
        required=True,
        initial='email',
    )
    config_oidc_phone_field = forms.CharField(
        label=pgettext_lazy('sso_oidc', 'Phone field'),
        required=False,
    )
    config_oidc_query_parameters = forms.CharField(
        label=pgettext_lazy('sso_oidc', 'Query parameters'),
        help_text=pgettext_lazy('sso_oidc', 'Optional query parameters, that will be added to calls to '
                                            'the authorization endpoint. Enter as: {example}'.format(
                                                example='<code>param1=value1&amp;param2=value2</code>'
                                            ),
                                ),
        required=False,
    )

    class Meta:
        model = CustomerSSOProvider
        fields = ['is_active', 'name', 'button_label', 'method']
        widgets = {
            'method': forms.RadioSelect,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        name_scheme = self.event.settings.name_scheme
        scheme = PERSON_NAME_SCHEMES.get(name_scheme)
        for fname, label, size in scheme['fields']:
            self.fields[f'config_oidc_{fname}_field'] = forms.CharField(
                label=pgettext_lazy('sso_oidc', f'{label} field').format(label=label),
                required=False,
            )

        self.fields['method'].choices = [c for c in self.fields['method'].choices if c[0]]

        for fname, f in self.fields.items():
            if fname.startswith('config_'):
                prefix, method, suffix = fname.split('_', 2)
                f.widget.attrs['data-display-dependency'] = f'input[name=method][value={method}]'

                if self.instance and self.instance.method == method:
                    f.initial = self.instance.configuration.get(suffix)

    def _unmask_secret_fields(self):
        for k, v in self.cleaned_data.items():
            if isinstance(self.fields.get(k), SecretKeySettingsField) and self.cleaned_data.get(k) == SECRET_REDACTED:
                self.cleaned_data[k] = self.fields[k].initial

    def clean(self):
        self._unmask_secret_fields()
        data = self.cleaned_data
        if not data.get("method"):
            return data

        config = {}
        for fname, f in self.fields.items():
            if fname.startswith(f'config_{data["method"]}_'):
                prefix, method, suffix = fname.split('_', 2)
                config[suffix] = data.get(fname)

        if data["method"] == "oidc":
            oidc_validate_and_complete_config(config)

        self.instance.configuration = config


class SSOClientForm(I18nModelForm):
    regenerate_client_secret = forms.BooleanField(
        label=_('Invalidate old client secret and generate a new one'),
        required=False,
    )

    class Meta:
        model = CustomerSSOClient
        fields = ['is_active', 'name', 'client_id', 'client_type', 'authorization_grant_type', 'redirect_uris',
                  'allowed_scopes', 'require_pkce']
        widgets = {
            'authorization_grant_type': forms.RadioSelect,
            'client_type': forms.RadioSelect,
            'allowed_scopes': forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['allowed_scopes'] = forms.MultipleChoiceField(
            label=self.fields['allowed_scopes'].label,
            help_text=self.fields['allowed_scopes'].help_text,
            required=self.fields['allowed_scopes'].required,
            initial=self.fields['allowed_scopes'].initial,
            choices=CustomerSSOClient.SCOPE_CHOICES,
            widget=forms.CheckboxSelectMultiple
        )
        if self.instance and self.instance.pk:
            self.fields['client_id'].disabled = True
        else:
            del self.fields['client_id']
            del self.fields['regenerate_client_secret']


class GiftCardAcceptanceInviteForm(forms.Form):
    acceptor = forms.CharField(
        label=_("Organizer short name"),
        required=True,
    )
    reusable_media = forms.BooleanField(
        label=_("Allow access to reusable media"),
        help_text=_("This is required if you want the other organizer to participate in a shared system with e.g. "
                    "NFC payment chips. You should only use this option for organizers you trust, since (depending "
                    "on the activated medium types) this will grant the other organizer access to cryptographic key "
                    "material required to interact with the media type."),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        self.organizer = kwargs.pop('organizer')
        super().__init__(*args, **kwargs)

    def clean_acceptor(self):
        val = self.cleaned_data['acceptor']
        try:
            acceptor = Organizer.objects.exclude(pk=self.organizer.pk).get(slug=val)
        except Organizer.DoesNotExist:
            raise ValidationError(_('The selected organizer does not exist or cannot be invited.'))
        if self.organizer.gift_card_acceptor_acceptance.filter(acceptor=acceptor).exists():
            raise ValidationError(_('The selected organizer has already been invited.'))
        return acceptor


class SalesChannelForm(I18nModelForm):
    class Meta:
        model = SalesChannel
        fields = ['label', 'identifier']
        widgets = {
            'default': forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        self.type = kwargs.pop("type")
        super().__init__(*args, **kwargs)

        if not self.type.multiple_allowed or (self.instance and self.instance.pk):
            self.fields["identifier"].initial = self.type.identifier
            self.fields["identifier"].disabled = True
            self.fields["label"].initial = LazyI18nString.from_gettext(self.type.verbose_name)

    def clean(self):
        d = super().clean()

        if self.instance.pk:
            d["identifier"] = self.instance.identifier
        elif self.type.multiple_allowed:
            d["identifier"] = self.type.identifier + "." + d["identifier"]
        else:
            d["identifier"] = self.type.identifier

        if not self.instance.pk:
            # self.event is actually the organizer, sorry I18nModelForm!
            if self.event.sales_channels.filter(identifier=d["identifier"]).exists():
                raise ValidationError(
                    _("A sales channel with the same identifier already exists.")
                )

        return d


class OrganizerPluginEventsForm(forms.Form):
    events = SafeEventMultipleChoiceField(
        queryset=Event.objects.none(),
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'scrolling-multiple-choice scrolling-multiple-choice-large',
        }),
        label=_("Events with active plugin"),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        events = kwargs.pop('events')
        super().__init__(*args, **kwargs)
        self.fields['events'].queryset = events
