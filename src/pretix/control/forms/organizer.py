from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils.translation import ugettext_lazy as _
from i18nfield.forms import I18nFormField, I18nTextarea

from pretix.base.forms import I18nModelForm, SettingsForm
from pretix.base.models import Organizer, Team
from pretix.control.forms import ExtFileField
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
        if Organizer.objects.filter(slug=slug).exists():
            raise forms.ValidationError(
                self.error_messages['duplicate_slug'],
                code='duplicate_slug',
            )
        return slug


class OrganizerUpdateForm(OrganizerForm):

    def __init__(self, *args, **kwargs):
        self.domain = kwargs.pop('domain', False)
        kwargs.setdefault('initial', {})
        self.instance = kwargs['instance']
        if self.domain and self.instance:
            initial_domain = self.instance.domains.first()
            if initial_domain:
                kwargs['initial'].setdefault('domain', initial_domain.domainname)

        super().__init__(*args, **kwargs)
        self.fields['slug'].widget.attrs['readonly'] = 'readonly'
        if self.domain:
            self.fields['domain'] = forms.CharField(
                max_length=255,
                label=_('Custom domain'),
                required=False,
                help_text=_('You need to configure the custom domain in the webserver beforehand.')
            )

    def clean_slug(self):
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
        self.fields['limit_events'].queryset = organizer.events.all()

    class Meta:
        model = Team
        fields = ['name', 'all_events', 'limit_events', 'can_create_events',
                  'can_change_teams', 'can_change_organizer_settings',
                  'can_change_event_settings', 'can_change_items',
                  'can_view_orders', 'can_change_orders',
                  'can_view_vouchers', 'can_change_vouchers']
        widgets = {
            'limit_events': forms.CheckboxSelectMultiple(attrs={
                'data-inverse-dependency': '#id_all_events'
            }),
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


class OrganizerSettingsForm(SettingsForm):

    organizer_info_text = I18nFormField(
        label=_('Info text'),
        required=False,
        widget=I18nTextarea,
        help_text=_('Not displayed anywhere by default, but if you want to, you can use this e.g. in ticket templates.')
    )


class OrganizerDisplaySettingsForm(SettingsForm):
    primary_color = forms.CharField(
        label=_("Primary color"),
        required=False,
        validators=[
            RegexValidator(regex='^#[0-9a-fA-F]{6}$',
                           message=_('Please enter the hexadecimal code of a color, e.g. #990000.'))
        ],
        widget=forms.TextInput(attrs={'class': 'colorpickerfield'})
    )
    organizer_homepage_text = I18nFormField(
        label=_('Homepage text'),
        required=False,
        widget=I18nTextarea,
        help_text=_('This will be displayed on the organizer homepage.')
    )
    organizer_logo_image = ExtFileField(
        label=_('Logo image'),
        ext_whitelist=(".png", ".jpg", ".gif", ".jpeg"),
        required=False,
        help_text=_('If you provide a logo image, we will by default not show your organization name '
                    'in the page header. We will show your logo with a maximal height of 120 pixels.')
    )
    event_list_type = forms.ChoiceField(
        label=_('Default overview style'),
        choices=(
            ('list', _('List')),
            ('calendar', _('Calendar'))
        )
    )
    locales = forms.MultipleChoiceField(
        choices=settings.LANGUAGES,
        label=_("Use languages"),
        widget=forms.CheckboxSelectMultiple,
        help_text=_('Choose all languages that your organizer homepage should be available in.')
    )
    primary_font = forms.ChoiceField(
        label=_('Font'),
        choices=[
            ('Open Sans', 'Open Sans')
        ],
        help_text=_('Only respected by modern browsers.')
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['primary_font'].choices += [
            (a, a) for a in get_fonts()
        ]
