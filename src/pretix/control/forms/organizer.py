from decimal import Decimal
from urllib.parse import urlparse

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db.models import Q
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_scopes.forms import SafeModelMultipleChoiceField
from i18nfield.forms import I18nFormField, I18nTextarea

from pretix.api.models import WebHook
from pretix.api.webhooks import get_all_webhook_events
from pretix.base.forms import I18nModelForm, SettingsForm
from pretix.base.models import Device, GiftCard, Organizer, Team
from pretix.control.forms import (
    ExtFileField, FontSelect, MultipleLanguagesWidget,
)
from pretix.control.forms.event import SafeEventMultipleChoiceField
from pretix.multidomain.models import KnownDomain
from pretix.presale.style import get_fonts


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


class DeviceForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        organizer = kwargs.pop('organizer')
        super().__init__(*args, **kwargs)
        self.fields['limit_events'].queryset = organizer.events.all().order_by(
            '-has_subevents', '-date_from'
        )

    def clean(self):
        d = super().clean()
        if not d['all_events'] and not d['limit_events']:
            raise ValidationError(_('Your device will not have access to anything, please select some events.'))

        return d

    class Meta:
        model = Device
        fields = ['name', 'all_events', 'limit_events']
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

    organizer_info_text = I18nFormField(
        label=_('Info text'),
        required=False,
        widget=I18nTextarea,
        help_text=_('Not displayed anywhere by default, but if you want to, you can use this e.g. in ticket templates.')
    )

    event_team_provisioning = forms.BooleanField(
        label=_('Allow creating a new team during event creation'),
        help_text=_('Users that do not have access to all events under this organizer, must select one of their teams '
                    'to have access to the created event. This setting allows users to create an event-specified team'
                    ' on-the-fly, even when they do not have \"Can change teams and permissions\" permission.'),
        required=False,
    )

    primary_color = forms.CharField(
        label=_("Primary color"),
        required=False,
        validators=[
            RegexValidator(regex='^#[0-9a-fA-F]{6}$',
                           message=_('Please enter the hexadecimal code of a color, e.g. #990000.')),
        ],
        widget=forms.TextInput(attrs={'class': 'colorpickerfield'})
    )
    theme_color_success = forms.CharField(
        label=_("Accent color for success"),
        help_text=_("We strongly suggest to use a shade of green."),
        required=False,
        validators=[
            RegexValidator(regex='^#[0-9a-fA-F]{6}$',
                           message=_('Please enter the hexadecimal code of a color, e.g. #990000.')),
        ],
        widget=forms.TextInput(attrs={'class': 'colorpickerfield'})
    )
    theme_color_danger = forms.CharField(
        label=_("Accent color for errors"),
        help_text=_("We strongly suggest to use a shade of red."),
        required=False,
        validators=[
            RegexValidator(regex='^#[0-9a-fA-F]{6}$',
                           message=_('Please enter the hexadecimal code of a color, e.g. #990000.')),

        ],
        widget=forms.TextInput(attrs={'class': 'colorpickerfield'})
    )
    theme_color_background = forms.CharField(
        label=_("Page background color"),
        required=False,
        validators=[
            RegexValidator(regex='^#[0-9a-fA-F]{6}$',
                           message=_('Please enter the hexadecimal code of a color, e.g. #990000.')),

        ],
        widget=forms.TextInput(attrs={'class': 'colorpickerfield no-contrast'})
    )
    theme_round_borders = forms.BooleanField(
        label=_("Use round edges"),
        required=False,
    )
    organizer_homepage_text = I18nFormField(
        label=_('Homepage text'),
        required=False,
        widget=I18nTextarea,
        help_text=_('This will be displayed on the organizer homepage.')
    )
    organizer_logo_image = ExtFileField(
        label=_('Header image'),
        ext_whitelist=(".png", ".jpg", ".gif", ".jpeg"),
        required=False,
        help_text=_('If you provide a logo image, we will by default not show your organization name '
                    'in the page header. By default, we show your logo with a size of up to 1140x120 pixels. You '
                    'can increase the size with the setting below. We recommend not using small details on the picture '
                    'as it will be resized on smaller screens.')
    )
    organizer_logo_image_large = forms.BooleanField(
        label=_('Use header image in its full size'),
        help_text=_('We recommend to upload a picture at least 1170 pixels wide.'),
        required=False,
    )
    event_list_type = forms.ChoiceField(
        label=_('Default overview style'),
        choices=(
            ('list', _('List')),
            ('calendar', _('Calendar'))
        )
    )
    event_list_availability = forms.BooleanField(
        label=_('Show availability in event overviews'),
        help_text=_('If checked, the list of events will show if events are sold out. This might '
                    'make for longer page loading times if you have lots of events and the shown status might be out '
                    'of date for up to two minutes.'),
        required=False
    )
    organizer_link_back = forms.BooleanField(
        label=_('Link back to organizer overview on all event pages'),
        required=False
    )
    locales = forms.MultipleChoiceField(
        choices=settings.LANGUAGES,
        label=_("Use languages"),
        widget=MultipleLanguagesWidget,
        help_text=_('Choose all languages that your organizer homepage should be available in.')
    )
    primary_font = forms.ChoiceField(
        label=_('Font'),
        choices=[
            ('Open Sans', 'Open Sans')
        ],
        widget=FontSelect,
        help_text=_('Only respected by modern browsers.')
    )
    favicon = ExtFileField(
        label=_('Favicon'),
        ext_whitelist=(".ico", ".png", ".jpg", ".gif", ".jpeg"),
        required=False,
        help_text=_('If you provide a favicon, we will show it instead of the default pretix icon. '
                    'We recommend a size of at least 200x200px to accomodate most devices.')
    )
    giftcard_length = forms.IntegerField(
        label=_('Length of gift card codes'),
        help_text=_('The system generates by default {}-character long gift card codes. However, if a different length '
                    'is required, it can be set here.'.format(settings.ENTROPY['giftcard_secret'])),
        required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['primary_font'].choices += [
            (a, {"title": a, "data": v}) for a, v in get_fonts().items()
        ]


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
        fields = ['secret', 'currency', 'testmode']
