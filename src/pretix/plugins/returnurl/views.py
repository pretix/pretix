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
import re

from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from pretix.base.forms import SettingsForm
from pretix.base.models import Event
from pretix.control.views.event import (
    EventSettingsFormView, EventSettingsViewMixin,
)


class ReturnSettingsForm(SettingsForm):
    returnurl_prefix = forms.CharField(
        label=_("Base redirection URLs"),
        help_text=_("Redirection will only be allowed to URLs that start with one of these prefixes. "
                    "Enter one allowed URL prefix per line. "
                    "URL prefixes must include a slash after the hostname."),
        required=False,
        widget=forms.Textarea,
    )
    line_regex = re.compile(r'^(https://.*/.*|http://localhost(:[0-9]+)?/.*)$')

    def clean_returnurl_prefix(self):
        val = self.cleaned_data['returnurl_prefix']
        for l in val.split("\n"):
            if not re.match(self.line_regex, l):
                raise ValidationError(_('All values must be URLs that include at last one slash after the hostname.'))
        return val


class ReturnSettings(EventSettingsViewMixin, EventSettingsFormView):
    model = Event
    form_class = ReturnSettingsForm
    template_name = 'returnurl/settings.html'
    permission = 'event.settings.general:write'

    def get_success_url(self) -> str:
        return reverse('plugins:returnurl:settings', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug
        })
