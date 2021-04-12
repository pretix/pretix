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
# This file contains Apache-licensed contributions copyrighted by: Jakob Schnell, Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from collections import OrderedDict

from django import forms
from django.utils.translation import gettext_lazy as _
from i18nfield.forms import I18nFormField, I18nTextarea, I18nTextInput

from pretix.base.forms import SecretKeySettingsField, SettingsForm
from pretix.base.settings import GlobalSettingsObject
from pretix.base.signals import register_global_settings


class GlobalSettingsForm(SettingsForm):
    auto_fields = [
        'region'
    ]

    def __init__(self, *args, **kwargs):
        self.obj = GlobalSettingsObject()
        super().__init__(*args, obj=self.obj, **kwargs)

        self.fields = OrderedDict(list(self.fields.items()) + [
            ('footer_text', I18nFormField(
                widget=I18nTextInput,
                required=False,
                label=_("Additional footer text"),
                help_text=_("Will be included as additional text in the footer, site-wide.")
            )),
            ('footer_link', I18nFormField(
                widget=I18nTextInput,
                required=False,
                label=_("Additional footer link"),
                help_text=_("Will be included as the link in the additional footer text.")
            )),
            ('banner_message', I18nFormField(
                widget=I18nTextarea,
                required=False,
                label=_("Global message banner"),
            )),
            ('banner_message_detail', I18nFormField(
                widget=I18nTextarea,
                required=False,
                label=_("Global message banner detail text"),
            )),
            ('opencagedata_apikey', SecretKeySettingsField(
                required=False,
                label=_("OpenCage API key for geocoding"),
            )),
            ('mapquest_apikey', SecretKeySettingsField(
                required=False,
                label=_("MapQuest API key for geocoding"),
            )),
            ('leaflet_tiles', forms.CharField(
                required=False,
                label=_("Leaflet tiles URL pattern"),
                help_text=_("e.g. {sample}").format(sample="https://a.tile.openstreetmap.org/{z}/{x}/{y}.png")
            )),
            ('leaflet_tiles_attribution', forms.CharField(
                required=False,
                label=_("Leaflet tiles attribution"),
                help_text=_("e.g. {sample}").format(sample='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors')
            )),
        ])
        responses = register_global_settings.send(self)
        for r, response in sorted(responses, key=lambda r: str(r[0])):
            for key, value in response.items():
                # We need to be this explicit, since OrderedDict.update does not retain ordering
                self.fields[key] = value

        self.fields['banner_message'].widget.attrs['rows'] = '2'
        self.fields['banner_message_detail'].widget.attrs['rows'] = '3'


class UpdateSettingsForm(SettingsForm):
    update_check_perform = forms.BooleanField(
        required=False,
        label=_("Perform update checks"),
        help_text=_("During the update check, pretix will report an anonymous, unique installation ID, "
                    "the current version of pretix and your installed plugins and the number of active and "
                    "inactive events in your installation to servers operated by the pretix developers. We "
                    "will only store anonymous data, never any IP addresses and we will not know who you are "
                    "or where to find your instance. You can disable this behavior here at any time.")
    )
    update_check_email = forms.EmailField(
        required=False,
        label=_("E-mail notifications"),
        help_text=_("We will notify you at this address if we detect that a new update is available. This "
                    "address will not be transmitted to pretix.eu, the emails will be sent by this server "
                    "locally.")
    )

    def __init__(self, *args, **kwargs):
        self.obj = GlobalSettingsObject()
        super().__init__(*args, obj=self.obj, **kwargs)


class LicenseCheckForm(forms.Form):
    base_changes = forms.ChoiceField(
        required=True,
        label=_("Changes to pretix"),
        widget=forms.RadioSelect,
        choices=(
            ("no", _('This installation of pretix is running without any custom modifications or extensions '
                     '(except for installed plugins).')),
            ("yes", _('This installation of pretix includes changes or extensions made to the source code.')),
        )
    )
    usage = forms.ChoiceField(
        required=True,
        label=_("Usage of pretix"),
        widget=forms.RadioSelect,
        choices=(
            ("internally", _('I only use pretix to organize events which are executed by my own company or its '
                             'affiliated companies, or to sell products sold by my own company.')),
            ("saas", _('I use pretix to sell tickets of other event organizers (e.g. a ticketing company) or I offer '
                       'the functionality of pretix to others (e.g. a Software-as-a-Service company).')),
            ("unsure", _('I\'m not sure which option applies.')),
        )
    )
    base_license = forms.ChoiceField(
        required=True,
        label=_("License choice"),
        widget=forms.RadioSelect,
        choices=(
            ("agpl_addperm", _('I want to use pretix under the additional permission granted to everyone by the '
                               'copyright holders which allows me to not share modifications if I only use pretix '
                               'internally.')),
            ("agpl", _('I want to use pretix under the terms of the AGPLv3 license without restriction on the scope '
                       'of usage and therefore without making use of any additional permission.')),
            ("enterprise", _('I have obtained a paid pretix Enterprise license which is currently valid.'))
        )
    )
    plugins_free = forms.BooleanField(
        required=False,
        label=_("This installation of pretix has installed plugins which are available freely under a non-copyleft "
                "license (Apache License, MIT License, BSD license, …)."),
    )
    plugins_copyleft = forms.BooleanField(
        required=False,
        label=_("This installation of pretix has installed plugins which are available freely under a license with "
                "strong copyleft (GPL, AGPL, …)."),
    )
    plugins_own = forms.BooleanField(
        required=False,
        label=_("This installation of pretix has installed plugins which have been created internally or obtained under "
                "a proprietary license by a third party."),
    )
    plugins_enterprise = forms.BooleanField(
        required=False,
        label=_("This installation of pretix has installed pretix Enterprise plugins with a valid license."),
    )
    poweredby_name = forms.CharField(
        required=False,
        label=_('Footer: "powered by" name (optional)'),
        help_text=_('If you want the "powered by" message in the page footer to include the name of your company or '
                    'organization (if you made any changes to pretix), set the name here.')
    )
    poweredby_url = forms.URLField(
        required=False,
        label=_('Link for powered by name'),
        help_text=_('If you used the previous option, you can set an URL to link to in the footer.'),
    )
    source_notice = forms.CharField(
        required=False,
        label=_('Source code instructions'),
        widget=forms.Textarea(attrs={'rows': '6'}),
        help_text=_('If you use pretix under AGPLv3 terms, describe exactly how to download the current source code '
                    'of the site including all modifications and installed plugins. This will be publicly available. '
                    'Make sure to keep it up to date!'),
    )
