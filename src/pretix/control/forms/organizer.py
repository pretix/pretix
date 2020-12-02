from decimal import Decimal
from urllib.parse import urlparse

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_scopes.forms import SafeModelMultipleChoiceField

from pretix.api.models import WebHook
from pretix.api.webhooks import get_all_webhook_events
from pretix.base.forms import I18nModelForm, SettingsForm
from pretix.base.forms.widgets import SplitDateTimePickerWidget
from pretix.base.models import Device, Gate, GiftCard, Organizer, Team
from pretix.control.forms import ExtFileField, SplitDateTimeField
from pretix.control.forms.event import SafeEventMultipleChoiceField
from pretix.multidomain.models import KnownDomain


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
            initial_domain = self.instance.domains.first()
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
        fields = ['name', 'default']
        widgets = {
            'default': forms.TextInput()
        }


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
                  'can_manage_gift_cards',
                  'can_change_event_settings', 'can_change_items',
                  'can_view_orders', 'can_change_orders',
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


class OrganizerSettingsForm(SettingsForm):
    auto_fields = [
        'organizer_info_text',
        'event_list_type',
        'event_list_availability',
        'organizer_homepage_text',
        'organizer_link_back',
        'organizer_logo_image_large',
        'giftcard_length',
        'giftcard_expiry_years',
        'locales',
        'event_team_provisioning',
        'primary_color',
        'theme_color_success',
        'theme_color_danger',
        'theme_color_background',
        'theme_round_borders',
        'primary_font'

    ]

    organizer_logo_image = ExtFileField(
        label=_('Header image'),
        ext_whitelist=(".png", ".jpg", ".gif", ".jpeg"),
        max_size=10 * 1024 * 1024,
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
        max_size=1 * 1024 * 1024,
        help_text=_('If you provide a favicon, we will show it instead of the default pretix icon. '
                    'We recommend a size of at least 200x200px to accommodate most devices.')
    )


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
