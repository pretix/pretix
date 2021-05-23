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
# This file contains Apache-licensed contributions copyrighted by: Jan-Frederik Rieckers, Sohalt, Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from itertools import chain

from django import forms
from django.core.exceptions import ValidationError
from django.utils.encoding import force_str
from django.utils.formats import date_format
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from phonenumber_field.formfields import PhoneNumberField
from phonenumber_field.phonenumber import PhoneNumber
from phonenumbers import NumberParseException
from phonenumbers.data import _COUNTRY_CODE_TO_REGION_CODE

from pretix.base.forms.questions import (
    BaseInvoiceAddressForm, BaseQuestionsForm, WrappedPhoneNumberPrefixWidget,
    guess_country,
)
from pretix.base.i18n import get_babel_locale, language
from pretix.base.validators import EmailBanlistValidator
from pretix.presale.signals import contact_form_fields


class ContactForm(forms.Form):
    required_css_class = 'required'
    email = forms.EmailField(label=_('E-mail'),
                             validators=[EmailBanlistValidator()],
                             widget=forms.EmailInput(attrs={'autocomplete': 'section-contact email'})
                             )

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        self.request = kwargs.pop('request')
        self.all_optional = kwargs.pop('all_optional', False)
        super().__init__(*args, **kwargs)

        if self.event.settings.order_email_asked_twice:
            self.fields['email_repeat'] = forms.EmailField(
                label=_('E-mail address (repeated)'),
                help_text=_('Please enter the same email address again to make sure you typed it correctly.'),
            )

        if self.event.settings.order_phone_asked:
            with language(get_babel_locale()):
                default_country = guess_country(self.event)
                default_prefix = None
                for prefix, values in _COUNTRY_CODE_TO_REGION_CODE.items():
                    if str(default_country) in values:
                        default_prefix = prefix
                try:
                    initial = self.initial.pop('phone', None)
                    initial = PhoneNumber().from_string(initial) if initial else "+{}.".format(default_prefix)
                except NumberParseException:
                    initial = None
                self.fields['phone'] = PhoneNumberField(
                    label=_('Phone number'),
                    required=self.event.settings.order_phone_required,
                    help_text=self.event.settings.checkout_phone_helptext,
                    # We now exploit an implementation detail in PhoneNumberPrefixWidget to allow us to pass just
                    # a country code but no number as an initial value. It's a bit hacky, but should be stable for
                    # the future.
                    initial=initial,
                    widget=WrappedPhoneNumberPrefixWidget()
                )

        if not self.request.session.get('iframe_session', False):
            # There is a browser quirk in Chrome that leads to incorrect initial scrolling in iframes if there
            # is an autofocus field. Who would have thought… See e.g. here:
            # https://floatboxjs.com/forum/topic.php?post=8440&usebb_sid=2e116486a9ec6b7070e045aea8cded5b#post8440
            self.fields['email'].widget.attrs['autofocus'] = 'autofocus'
        self.fields['email'].help_text = self.event.settings.checkout_email_helptext

        responses = contact_form_fields.send(self.event, request=self.request)
        for r, response in responses:
            for key, value in response.items():
                # We need to be this explicit, since OrderedDict.update does not retain ordering
                self.fields[key] = value
        if self.all_optional:
            for k, v in self.fields.items():
                v.required = False
                v.widget.is_required = False

    def clean(self):
        if self.event.settings.order_email_asked_twice and self.cleaned_data.get('email') and self.cleaned_data.get('email_repeat'):
            if self.cleaned_data.get('email').lower() != self.cleaned_data.get('email_repeat').lower():
                raise ValidationError(_('Please enter the same email address twice.'))


class InvoiceAddressForm(BaseInvoiceAddressForm):
    required_css_class = 'required'
    vat_warning = True

    def __init__(self, *args, **kwargs):
        allow_save = kwargs.pop('allow_save', False)
        super().__init__(*args, **kwargs)
        if allow_save:
            self.fields['saved_id'] = forms.IntegerField(required=False, widget=forms.HiddenInput)
            self.fields['save'] = forms.BooleanField(
                label=_('Save address in my customer account for future purchases'),
                required=False,
                initial=True,
            )


class InvoiceNameForm(InvoiceAddressForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in list(self.fields.keys()):
            if f != 'name_parts':
                del self.fields[f]


class QuestionsForm(BaseQuestionsForm):
    """
    This form class is responsible for asking order-related questions. This includes
    the attendee name for admission tickets, if the corresponding setting is enabled,
    as well as additional questions defined by the organizer.
    """
    required_css_class = 'required'

    def __init__(self, *args, **kwargs):
        allow_save = kwargs.pop('allow_save', False)
        super().__init__(*args, **kwargs)
        if allow_save and self.fields:
            self.fields['saved_id'] = forms.IntegerField(required=False, widget=forms.HiddenInput)
            self.fields['save'] = forms.BooleanField(
                label=_('Save profile in my customer account for future purchases'),
                required=False,
                initial=True,
            )


class AddOnRadioSelect(forms.RadioSelect):
    option_template_name = 'pretixpresale/forms/addon_choice_option.html'

    def optgroups(self, name, value, attrs=None):
        attrs = attrs or {}
        groups = []
        has_selected = False
        for index, (option_value, option_label, option_desc) in enumerate(chain(self.choices)):
            if option_value is None:
                option_value = ''
            if isinstance(option_label, (list, tuple)):
                raise TypeError('Choice groups are not supported here')
            group_name = None
            subgroup = []
            groups.append((group_name, subgroup, index))

            selected = (
                force_str(option_value) in value and
                (has_selected is False or self.allow_multiple_selected)
            )
            if selected is True and has_selected is False:
                has_selected = True
            attrs['description'] = option_desc
            subgroup.append(self.create_option(
                name, option_value, option_label, selected, index,
                subindex=None, attrs=attrs,
            ))

        return groups


class AddOnVariationField(forms.ChoiceField):
    def valid_value(self, value):
        text_value = force_str(value)
        for k, v, d in self.choices:
            if value == k or text_value == force_str(k):
                return True
        return False


class MembershipForm(forms.Form):
    required_css_class = 'required'

    def __init__(self, *args, **kwargs):
        self.memberships = kwargs.pop('memberships')
        event = kwargs.pop('event')
        self.position = kwargs.pop('position')

        super().__init__(*args, **kwargs)

        ev = self.position.subevent or event
        if self.position.variation and self.position.variation.require_membership:
            types = self.position.variation.require_membership_types.all()
        else:
            types = self.position.item.require_membership_types.all()

        initial = None

        memberships = [
            m for m in self.memberships
            if m.is_valid(ev) and m.membership_type in types
        ]

        if len(memberships) == 1:
            initial = str(memberships[0].pk)

        self.fields['membership'] = forms.ChoiceField(
            label=_('Membership'),
            choices=[
                (str(m.pk), self._label_from_instance(m))
                for m in memberships
            ],
            initial=initial,
            widget=forms.RadioSelect,
        )
        self.is_empty = not memberships

    def _label_from_instance(self, obj):
        ds = date_format(obj.date_start, 'SHORT_DATE_FORMAT')
        de = date_format(obj.date_end, 'SHORT_DATE_FORMAT')
        if obj.membership_type.max_usages is not None:
            usages = f'({obj.usages} / {obj.membership_type.max_usages})'
        else:
            usages = ''
        d = f'<strong>{escape(obj.membership_type)}</strong> {usages}<br>'
        if obj.attendee_name:
            d += f'{escape(obj.attendee_name)}<br>'
        d += f'<span class="text-muted">{ds} – {de}</span>'
        if obj.testmode:
            d += ' <span class="label label-warning">{}</span>'.format(_("TEST MODE"))
        return mark_safe(d)

    def clean(self):
        d = super().clean()
        if d.get('membership'):
            d['membership'] = [m for m in self.memberships if str(m.pk) == d['membership']][0]
        return d
