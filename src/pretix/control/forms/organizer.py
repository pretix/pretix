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
from django.forms import inlineformset_factory
from django.forms.utils import ErrorDict
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_scopes.forms import (
    SafeModelChoiceField, SafeModelMultipleChoiceField,
)
from i18nfield.forms import (
    I18nFormField, I18nFormSetMixin, I18nTextarea, I18nTextInput,
)
from phonenumber_field.formfields import PhoneNumberField
from pytz import common_timezones

from pretix.api.models import WebHook
from pretix.api.webhooks import get_all_webhook_events
from pretix.base.customersso.oidc import oidc_validate_and_complete_config
from pretix.base.forms import I18nModelForm, PlaceholderValidator, SettingsForm
from pretix.base.forms.questions import (
    NamePartsFormField, WrappedPhoneNumberPrefixWidget, get_country_by_locale,
    get_phone_prefix,
)
from pretix.base.forms.widgets import SplitDateTimePickerWidget
from pretix.base.models import (
    Customer, Device, EventMetaProperty, Gate, GiftCard, GiftCardAcceptance,
    Membership, MembershipType, OrderPosition, Organizer, ReusableMedium, Team,
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
            current_domain = instance.domains.filter(event__isnull=True).first()
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


class SafeOrderPositionChoiceField(forms.ModelChoiceField):
    def __init__(self, queryset, **kwargs):
        queryset = queryset.model.all.none()
        super().__init__(queryset, **kwargs)

    def label_from_instance(self, op):
        return f'{op.order.code}-{op.positionid} ({str(op.item) + ((" - " + str(op.variation)) if op.variation else "")})'


class EventMetaPropertyForm(forms.ModelForm):
    class Meta:
        model = EventMetaProperty
        fields = ['name', 'default', 'required', 'protected', 'allowed_values', 'filter_allowed']
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

    mail_subject_customer_registration = I18nFormField(
        label=_("Subject"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_customer_registration = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nTextarea,
    )
    mail_subject_customer_email_change = I18nFormField(
        label=_("Subject"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_customer_email_change = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nTextarea,
    )
    mail_subject_customer_reset = I18nFormField(
        label=_("Subject"),
        required=False,
        widget=I18nTextInput,
    )
    mail_text_customer_reset = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nTextarea,
    )

    base_context = {
        'mail_text_customer_registration': ['customer', 'url'],
        'mail_subject_customer_registration': ['customer', 'url'],
        'mail_text_customer_email_change': ['customer', 'url'],
        'mail_subject_customer_email_change': ['customer', 'url'],
        'mail_text_customer_reset': ['customer', 'url'],
        'mail_subject_customer_reset': ['customer', 'url'],
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
        if self.instance and self.instance.pk:
            self.fields['events'].initial = list(self.instance.listeners.values_list('action_type', flat=True))

    class Meta:
        model = WebHook
        fields = ['target_url', 'enabled', 'all_events', 'limit_events', 'comment']
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
        min_value=Decimal('0.00'),
        max_value=Decimal('99999999.99'),
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
        fields = ['expires', 'conditions', 'owner_ticket']
        field_classes = {
            'expires': SplitDateTimeField,
            'owner_ticket': SafeOrderPositionChoiceField,
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
                'data-placeholder': _('Ticket')
            }
        )
        self.fields['owner_ticket'].widget.choices = self.fields['owner_ticket'].choices
        self.fields['owner_ticket'].required = False


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
                'data-placeholder': _('Ticket')
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
                'data-placeholder': _('Gift card')
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
                    'data-placeholder': _('Customer')
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
    config_oidc_client_secret = forms.CharField(
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

    def clean(self):
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
                  'allowed_scopes']
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
