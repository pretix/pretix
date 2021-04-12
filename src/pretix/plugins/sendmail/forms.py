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
# This file contains Apache-licensed contributions copyrighted by: Alexey Kislitsin, Daniel, Flavia Bastos, Sanket
# Dasgupta, Sohalt, pajowu
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_scopes.forms import SafeModelMultipleChoiceField
from i18nfield.forms import I18nFormField, I18nTextarea, I18nTextInput

from pretix.base.email import get_available_placeholders
from pretix.base.forms import PlaceholderValidator
from pretix.base.forms.widgets import SplitDateTimePickerWidget
from pretix.base.models import CheckinList, Item, Order, SubEvent
from pretix.control.forms import CachedFileField
from pretix.control.forms.widgets import Select2, Select2Multiple


class MailForm(forms.Form):
    recipients = forms.ChoiceField(
        label=_('Send email to'),
        widget=forms.RadioSelect,
        initial='orders',
        choices=[]
    )
    sendto = forms.MultipleChoiceField()  # overridden later
    subject = forms.CharField(label=_("Subject"))
    message = forms.CharField(label=_("Message"))
    attachment = CachedFileField(
        label=_("Attachment"),
        required=False,
        ext_whitelist=(
            ".png", ".jpg", ".gif", ".jpeg", ".pdf", ".txt", ".docx", ".gif", ".svg",
            ".pptx", ".ppt", ".doc", ".xlsx", ".xls", ".jfif", ".heic", ".heif", ".pages",
            ".bmp", ".tif", ".tiff"
        ),
        help_text=_('Sending an attachment increases the chance of your email not arriving or being sorted into spam folders. We recommend only using PDFs '
                    'of no more than 2 MB in size.'),
        max_size=10 * 1024 * 1024
    )  # TODO i18n
    items = forms.ModelMultipleChoiceField(
        widget=forms.CheckboxSelectMultiple(
            attrs={'class': 'scrolling-multiple-choice'}
        ),
        label=_('Only send to people who bought'),
        required=True,
        queryset=Item.objects.none()
    )
    filter_checkins = forms.BooleanField(
        label=_('Filter check-in status'),
        required=False
    )
    checkin_lists = SafeModelMultipleChoiceField(queryset=CheckinList.objects.none(), required=False)  # overridden later
    not_checked_in = forms.BooleanField(label=_("Send to customers not checked in"), required=False)
    subevent = forms.ModelChoiceField(
        SubEvent.objects.none(),
        label=_('Only send to customers of'),
        required=False,
        empty_label=pgettext_lazy('subevent', 'All dates')
    )
    subevents_from = forms.SplitDateTimeField(
        widget=SplitDateTimePickerWidget(),
        label=pgettext_lazy('subevent', 'Only send to customers of dates starting at or after'),
        required=False,
    )
    subevents_to = forms.SplitDateTimeField(
        widget=SplitDateTimePickerWidget(),
        label=pgettext_lazy('subevent', 'Only send to customers of dates starting before'),
        required=False,
    )
    created_from = forms.SplitDateTimeField(
        widget=SplitDateTimePickerWidget(),
        label=pgettext_lazy('subevent', 'Only send to customers with orders created after'),
        required=False,
    )
    created_to = forms.SplitDateTimeField(
        widget=SplitDateTimePickerWidget(),
        label=pgettext_lazy('subevent', 'Only send to customers with orders created before'),
        required=False,
    )

    def clean(self):
        d = super().clean()
        if d.get('subevent') and (d.get('subevents_from') or d.get('subevents_to')):
            raise ValidationError(pgettext_lazy('subevent', 'Please either select a specific date or a date range, not both.'))
        if bool(d.get('subevents_from')) != bool(d.get('subevents_to')):
            raise ValidationError(pgettext_lazy('subevent', 'If you set a date range, please set both a start and an end.'))
        return d

    def _set_field_placeholders(self, fn, base_parameters):
        phs = [
            '{%s}' % p
            for p in sorted(get_available_placeholders(self.event, base_parameters).keys())
        ]
        ht = _('Available placeholders: {list}').format(
            list=', '.join(phs)
        )
        if self.fields[fn].help_text:
            self.fields[fn].help_text += ' ' + str(ht)
        else:
            self.fields[fn].help_text = ht
        self.fields[fn].validators.append(
            PlaceholderValidator(phs)
        )

    def __init__(self, *args, **kwargs):
        event = self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)

        recp_choices = [
            ('orders', _('Everyone who created a ticket order'))
        ]
        if event.settings.attendee_emails_asked:
            recp_choices += [
                ('attendees', _('Every attendee (falling back to the order contact when no attendee email address is '
                                'given)')),
                ('both', _('Both (all order contact addresses and all attendee email addresses)'))
            ]
        self.fields['recipients'].choices = recp_choices

        self.fields['subject'] = I18nFormField(
            label=_('Subject'),
            widget=I18nTextInput, required=True,
            locales=event.settings.get('locales'),
        )
        self.fields['message'] = I18nFormField(
            label=_('Message'),
            widget=I18nTextarea, required=True,
            locales=event.settings.get('locales'),
        )
        self._set_field_placeholders('subject', ['event', 'order', 'position_or_address'])
        self._set_field_placeholders('message', ['event', 'order', 'position_or_address'])
        choices = [(e, l) for e, l in Order.STATUS_CHOICE if e != 'n']
        choices.insert(0, ('na', _('payment pending (except unapproved)')))
        choices.insert(0, ('pa', _('approval pending')))
        if not event.settings.get('payment_term_expire_automatically', as_type=bool):
            choices.append(
                ('overdue', _('pending with payment overdue'))
            )
        self.fields['sendto'] = forms.MultipleChoiceField(
            label=_("Send to customers with order status"),
            widget=forms.CheckboxSelectMultiple(
                attrs={'class': 'scrolling-multiple-choice'}
            ),
            choices=choices
        )
        if not self.initial.get('sendto'):
            self.initial['sendto'] = ['p', 'na']
        elif 'n' in self.initial['sendto']:
            self.initial['sendto'].append('pa')
            self.initial['sendto'].append('na')

        self.fields['items'].queryset = event.items.all()
        if not self.initial.get('items'):
            self.initial['items'] = event.items.all()

        self.fields['checkin_lists'].queryset = event.checkin_lists.all()
        self.fields['checkin_lists'].widget = Select2Multiple(
            attrs={
                'data-model-select2': 'generic',
                'data-select2-url': reverse('control:event.orders.checkinlists.select2', kwargs={
                    'event': event.slug,
                    'organizer': event.organizer.slug,
                }),
                'data-placeholder': _('Send to customers checked in on list'),
            }
        )
        self.fields['checkin_lists'].widget.choices = self.fields['checkin_lists'].choices
        self.fields['checkin_lists'].label = _('Send to customers checked in on list')

        if event.has_subevents:
            self.fields['subevent'].queryset = event.subevents.all()
            self.fields['subevent'].widget = Select2(
                attrs={
                    'data-model-select2': 'event',
                    'data-select2-url': reverse('control:event.subevents.select2', kwargs={
                        'event': event.slug,
                        'organizer': event.organizer.slug,
                    }),
                    'data-placeholder': pgettext_lazy('subevent', 'Date')
                }
            )
            self.fields['subevent'].widget.choices = self.fields['subevent'].choices
        else:
            del self.fields['subevent']
            del self.fields['subevents_from']
            del self.fields['subevents_to']
