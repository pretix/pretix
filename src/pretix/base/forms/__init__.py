import logging

import i18nfield.forms
from django import forms
from django.forms.models import ModelFormMetaclass
from django.utils import six
from django.utils.crypto import get_random_string
from formtools.wizard.views import SessionWizardView
from hierarkey.forms import HierarkeyForm

from pretix.base.reldate import RelativeDateField, RelativeDateTimeField

from .validators import PlaceholderValidator  # NOQA

logger = logging.getLogger(__name__)


class BaseI18nModelForm(i18nfield.forms.BaseI18nModelForm):
    # compatibility shim for django-i18nfield library

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event', None)
        if self.event:
            kwargs['locales'] = self.event.settings.get('locales')
        super().__init__(*args, **kwargs)


class I18nModelForm(six.with_metaclass(ModelFormMetaclass, BaseI18nModelForm)):
    pass


class I18nFormSet(i18nfield.forms.I18nModelFormSet):
    # compatibility shim for django-i18nfield library

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event', None)
        if self.event:
            kwargs['locales'] = self.event.settings.get('locales')
        super().__init__(*args, **kwargs)


class I18nInlineFormSet(i18nfield.forms.I18nInlineFormSet):
    # compatibility shim for django-i18nfield library

    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event', None)
        if event:
            kwargs['locales'] = event.settings.get('locales')
        super().__init__(*args, **kwargs)


class SettingsForm(i18nfield.forms.I18nFormMixin, HierarkeyForm):
    auto_fields = []

    def __init__(self, *args, **kwargs):
        from pretix.base.settings import DEFAULTS

        self.obj = kwargs.get('obj', None)
        self.locales = self.obj.settings.get('locales') if self.obj else kwargs.pop('locales', None)
        kwargs['attribute_name'] = 'settings'
        kwargs['locales'] = self.locales
        kwargs['initial'] = self.obj.settings.freeze()
        super().__init__(*args, **kwargs)
        for fname in self.auto_fields:
            kwargs = DEFAULTS[fname].get('form_kwargs', {})
            kwargs.setdefault('required', False)
            field = DEFAULTS[fname]['form_class'](
                **kwargs
            )
            if isinstance(field, i18nfield.forms.I18nFormField):
                field.widget.enabled_locales = self.locales
            self.fields[fname] = field
        for k, f in self.fields.items():
            if isinstance(f, (RelativeDateTimeField, RelativeDateField)):
                f.set_event(self.obj)

    def get_new_filename(self, name: str) -> str:
        from pretix.base.models import Event

        nonce = get_random_string(length=8)
        if isinstance(self.obj, Event):
            fname = '%s/%s/%s.%s.%s' % (
                self.obj.organizer.slug, self.obj.slug, name, nonce, name.split('.')[-1]
            )
        else:
            fname = '%s/%s.%s.%s' % (self.obj.slug, name, nonce, name.split('.')[-1])
        # TODO: make sure pub is always correct
        return 'pub/' + fname


class PrefixForm(forms.Form):
    prefix = forms.CharField(widget=forms.HiddenInput)


class SafeSessionWizardView(SessionWizardView):
    def get_prefix(self, request, *args, **kwargs):
        if hasattr(request, '_session_wizard_prefix'):
            return request._session_wizard_prefix
        prefix_form = PrefixForm(self.request.POST, prefix=super().get_prefix(request, *args, **kwargs))
        if not prefix_form.is_valid():
            request._session_wizard_prefix = get_random_string(length=24)
        else:
            request._session_wizard_prefix = prefix_form.cleaned_data['prefix']
        return request._session_wizard_prefix

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)
        context['wizard']['prefix_form'] = PrefixForm(
            prefix=super().get_prefix(self.request),
            initial={
                'prefix': self.get_prefix(self.request)
            }
        )
        return context
