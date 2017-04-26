from django import forms
from django.utils.translation import ugettext_lazy as _

from pretix.base.forms import I18nModelForm
from pretix.base.models import Organizer
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
            instance.get_cache().clear()

        return instance
