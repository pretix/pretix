from django import forms
from django.utils.translation import ugettext_lazy as _
from pretix.base.forms import VersionedModelForm

from pretix.base.models import Organizer


class OrganizerForm(VersionedModelForm):
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
        super().__init__(*args, **kwargs)
        self.fields['slug'].widget.attrs['disabled'] = 'disabled'

    def clean_slug(self):
        return self.instance.slug
