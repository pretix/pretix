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
from datetime import timedelta

from dateutil.rrule import DAILY, MONTHLY, WEEKLY, YEARLY, rrule, rrulestr
from django import forms
from django.utils.dates import MONTHS, WEEKDAYS
from django.utils.timezone import get_current_timezone, now
from django.utils.translation import gettext_lazy as _, pgettext_lazy


class RRuleForm(forms.Form):
    # TODO: calendar.setfirstweekday
    freq = forms.ChoiceField(
        choices=[
            ('yearly', _('year(s)')),
            ('monthly', _('month(s)')),
            ('weekly', _('week(s)')),
            ('daily', _('day(s)')),
        ],
        initial='weekly'
    )
    interval = forms.IntegerField(
        label=_('Interval'),
        initial=1,
        min_value=1,
        widget=forms.NumberInput(attrs={'min': '1'})
    )
    dtstart = forms.DateField(
        label=_('Start date'),
        widget=forms.DateInput(
            attrs={
                'class': 'datepickerfield',
                'required': 'required'
            }
        ),
        initial=lambda: now().astimezone(get_current_timezone()).date()
    )

    end = forms.ChoiceField(
        choices=[
            ('count', ''),
            ('until', ''),
            ('forever', ''),
        ],
        initial='count',
        widget=forms.RadioSelect
    )
    count = forms.IntegerField(
        label=_('Number of repetitions'),
        initial=10
    )
    until = forms.DateField(
        widget=forms.DateInput(
            attrs={
                'class': 'datepickerfield',
                'required': 'required'
            }
        ),
        label=_('Last date'),
        required=True,
        initial=lambda: now() + timedelta(days=30)
    )

    yearly_bysetpos = forms.ChoiceField(
        choices=[
            ('1', pgettext_lazy('rrule', 'first')),
            ('2', pgettext_lazy('rrule', 'second')),
            ('3', pgettext_lazy('rrule', 'third')),
            ('-1', pgettext_lazy('rrule', 'last')),
        ],
        required=False
    )
    yearly_same = forms.ChoiceField(
        choices=[
            ('on', ''),
            ('off', ''),
        ],
        initial='on',
        widget=forms.RadioSelect
    )
    yearly_byweekday = forms.ChoiceField(
        choices=[
            ('MO', WEEKDAYS[0]),
            ('TU', WEEKDAYS[1]),
            ('WE', WEEKDAYS[2]),
            ('TH', WEEKDAYS[3]),
            ('FR', WEEKDAYS[4]),
            ('SA', WEEKDAYS[5]),
            ('SU', WEEKDAYS[6]),
            ('MO,TU,WE,TH,FR,SA,SU', _('Day')),
            ('MO,TU,WE,TH,FR', _('Weekday')),
            ('SA,SU', _('Weekend day')),
        ],
        required=False
    )
    yearly_bymonth = forms.ChoiceField(
        choices=[
            (str(i), MONTHS[i]) for i in range(1, 13)
        ],
        required=False
    )

    monthly_same = forms.ChoiceField(
        choices=[
            ('on', ''),
            ('off', ''),
        ],
        initial='on',
        widget=forms.RadioSelect
    )
    monthly_bysetpos = forms.ChoiceField(
        choices=[
            ('1', pgettext_lazy('rrule', 'first')),
            ('2', pgettext_lazy('rrule', 'second')),
            ('3', pgettext_lazy('rrule', 'third')),
            ('-1', pgettext_lazy('rrule', 'last')),
        ],
        required=False
    )
    monthly_byweekday = forms.ChoiceField(
        choices=[
            ('MO', WEEKDAYS[0]),
            ('TU', WEEKDAYS[1]),
            ('WE', WEEKDAYS[2]),
            ('TH', WEEKDAYS[3]),
            ('FR', WEEKDAYS[4]),
            ('SA', WEEKDAYS[5]),
            ('SU', WEEKDAYS[6]),
            ('MO,TU,WE,TH,FR,SA,SU', _('Day')),
            ('MO,TU,WE,TH,FR', _('Weekday')),
            ('SA,SU', _('Weekend day')),
        ],
        required=False
    )

    weekly_byweekday = forms.MultipleChoiceField(
        choices=[
            ('MO', WEEKDAYS[0]),
            ('TU', WEEKDAYS[1]),
            ('WE', WEEKDAYS[2]),
            ('TH', WEEKDAYS[3]),
            ('FR', WEEKDAYS[4]),
            ('SA', WEEKDAYS[5]),
            ('SU', WEEKDAYS[6]),
        ],
        required=False,
        widget=forms.CheckboxSelectMultiple
    )

    def parse_weekdays(self, value):
        m = {
            'MO': 0,
            'TU': 1,
            'WE': 2,
            'TH': 3,
            'FR': 4,
            'SA': 5,
            'SU': 6
        }
        if ',' in value:
            return [m.get(a) for a in value.split(',')]
        else:
            return m.get(value)

    def to_rrule(self):
        rule_kwargs = {}
        rule_kwargs['dtstart'] = self.cleaned_data['dtstart']
        rule_kwargs['interval'] = self.cleaned_data['interval']

        if self.cleaned_data['freq'] == 'yearly':
            freq = YEARLY
            if self.cleaned_data['yearly_same'] == "off":
                rule_kwargs['bysetpos'] = int(self.cleaned_data['yearly_bysetpos'])
                rule_kwargs['byweekday'] = self.parse_weekdays(self.cleaned_data['yearly_byweekday'])
                rule_kwargs['bymonth'] = int(self.cleaned_data['yearly_bymonth'])

        elif self.cleaned_data['freq'] == 'monthly':
            freq = MONTHLY

            if self.cleaned_data['monthly_same'] == "off":
                rule_kwargs['bysetpos'] = int(self.cleaned_data['monthly_bysetpos'])
                rule_kwargs['byweekday'] = self.parse_weekdays(self.cleaned_data['monthly_byweekday'])
        elif self.cleaned_data['freq'] == 'weekly':
            freq = WEEKLY

            if self.cleaned_data['weekly_byweekday']:
                rule_kwargs['byweekday'] = [self.parse_weekdays(a) for a in self.cleaned_data['weekly_byweekday']]

        elif self.cleaned_data['freq'] == 'daily':
            freq = DAILY

        if self.cleaned_data['end'] == 'count':
            rule_kwargs['count'] = self.cleaned_data['count']
        elif self.cleaned_data['end'] == 'until':
            rule_kwargs['until'] = self.cleaned_data['until']
        return rrule(freq, **rule_kwargs)

    @staticmethod
    def initial_from_rrule(rule: rrule):
        initial = {}
        if isinstance(rule, str):
            rule = rrulestr(rule)

        _rule = rule._original_rule
        initial['dtstart'] = rule._dtstart
        initial['interval'] = rule._interval

        if rule._freq == YEARLY:
            initial['freq'] = 'yearly'
            initial['yearly_bysetpos'] = _rule.get('bysetpos')
            initial['yearly_byweekday'] = _rule.get('byweekday')
            initial['yearly_bymonth'] = _rule.get('bymonth')
        elif rule._freq == MONTHLY:
            initial['freq'] = 'monthly'
            initial['monthly_bysetpos'] = _rule.get('bysetpos')
            initial['monthly_byweekday'] = _rule.get('byweekday')
        elif rule._freq == WEEKLY:
            initial['freq'] = 'weekly'
            initial['weekly_byweekday'] = _rule.get('byweekday')
        elif rule._freq == DAILY:
            initial['freq'] = 'daily'

        if rule._count:
            initial['end'] = 'count'
            initial['count'] = rule._count
        elif rule._until:
            initial['end'] = 'until'
            initial['until'] = rule._until
        else:
            initial['end'] = 'forever'
        return initial
