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
# This file contains Apache-licensed contributions copyrighted by: Alexey Kislitsin, Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import logging

import i18nfield.forms
from django import forms
from django.core.validators import URLValidator
from django.forms.models import ModelFormMetaclass
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _
from formtools.wizard.views import SessionWizardView
from hierarkey.forms import HierarkeyForm
from i18nfield.strings import LazyI18nString

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


class I18nModelForm(BaseI18nModelForm, metaclass=ModelFormMetaclass):
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


SECRET_REDACTED = '*****'


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
            if callable(kwargs):
                kwargs = kwargs()
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

    def _unmask_secret_fields(self):
        for k, v in self.cleaned_data.items():
            if isinstance(self.fields.get(k), SecretKeySettingsField) and self.cleaned_data.get(k) == SECRET_REDACTED:
                self.cleaned_data[k] = self.initial[k]

    def save(self):
        self._unmask_secret_fields()
        return super().save()

    def clean(self):
        d = super().clean()

        # There is logic in HierarkeyForm.save() to only persist fields that changed. HierarkeyForm determines if
        # something changed by comparing `self._s.get(name)` to `value`. This leaves an edge case open for multi-lingual
        # text fields. On the very first load, the initial value in `self._s.get(name)` will be a LazyGettextProxy-based
        # string. However, only some of the languages are usually visible, so even if the user does not change anything
        # at all, it will be considered a changed value and stored. We do not want that, as it makes it very hard to add
        # languages to an organizer/event later on. So we trick it and make sure nothing gets changed in that situation.
        for name, field in self.fields.items():
            if isinstance(field, SecretKeySettingsField) and d.get(name) == SECRET_REDACTED and not self.initial.get(name):
                self.add_error(
                    name,
                    _('Due to technical reasons you cannot set inputs, that need to be masked (e.g. passwords), to %(value)s.') % {'value': SECRET_REDACTED}
                )

            if isinstance(field, i18nfield.forms.I18nFormField):
                value = d.get(name)
                if not value:
                    continue

                current = self._s.get(name, as_type=type(value))
                if name not in self.changed_data:
                    d[name] = current

        return d

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
    template_name = "django/forms/table.html"


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


class SecretKeySettingsWidget(forms.TextInput):
    def __init__(self, attrs=None):
        if attrs is None:
            attrs = {}
        attrs.update({
            'autocomplete': 'new-password'  # see https://bugs.chromium.org/p/chromium/issues/detail?id=370363#c7
        })
        self.__reflect_value = False
        super().__init__(attrs)

    def value_from_datadict(self, data, files, name):
        value = super().value_from_datadict(data, files, name)
        self.__reflect_value = value and value != SECRET_REDACTED
        return value

    def get_context(self, name, value, attrs):
        if value and not self.__reflect_value:
            value = SECRET_REDACTED
        return super().get_context(name, value, attrs)


class SecretKeySettingsField(forms.CharField):
    widget = SecretKeySettingsWidget

    def has_changed(self, initial, data):
        if data == SECRET_REDACTED:
            return False
        return super().has_changed(initial, data)

    def run_validators(self, value):
        if value == SECRET_REDACTED:
            return
        return super().run_validators(value)


class I18nURLFormField(i18nfield.forms.I18nFormField):
    def clean(self, value) -> LazyI18nString:
        value = super().clean(value)
        if not value:
            return value
        if isinstance(value.data, dict):
            for v in value.data.values():
                if v:
                    URLValidator()(v)
        else:
            URLValidator()(value.data)
        return value
