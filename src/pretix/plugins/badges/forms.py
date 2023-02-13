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
from django import forms
from django.forms import Field
from django.forms.models import ModelChoiceIterator
from django.utils.translation import gettext_lazy as _

from pretix.plugins.badges.models import BadgeItem, BadgeLayout


class BadgeLayoutForm(forms.ModelForm):
    class Meta:
        model = BadgeLayout
        fields = ('name',)


NoLayoutSingleton = BadgeLayout(pk='-')


class BadgeLayoutIterator(ModelChoiceIterator):

    def __iter__(self):
        yield ("-", _("(Do not print badges)"))
        yield from super().__iter__()

    def __len__(self):
        return super().__len__() + 1


class BadgeLayoutChoiceField(forms.ModelChoiceField):
    iterator = BadgeLayoutIterator

    def to_python(self, value):
        if value == '-':
            return NoLayoutSingleton
        return super().to_python(value)

    def validate(self, value):
        if value == '-':
            return '-'
        return Field.validate(self, value)


class BadgeItemForm(forms.ModelForm):
    is_layouts = True
    layout = BadgeLayoutChoiceField(queryset=BadgeLayout.objects.none())

    class Meta:
        model = BadgeItem
        fields = ('layout',)
        exclude = ('layout',)

    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event')
        super().__init__(*args, **kwargs)
        self.fields['layout'].label = _('Badge layout')
        self.fields['layout'].empty_label = _('(Event default)')
        self.fields['layout'].queryset = event.badge_layouts.all()
        self.fields['layout'].required = False
        if self.instance.pk and not self.instance.layout_id:
            self.initial['layout'] = NoLayoutSingleton
        elif self.instance.layout:
            self.initial['layout'] = self.instance.layout

    def save(self, commit=True):
        if self.cleaned_data['layout'] is None:
            if self.instance.pk:
                self.instance.delete()
            else:
                return
        elif self.cleaned_data['layout'] is NoLayoutSingleton:
            self.instance.layout = None
            self.instance.save()
        else:
            self.instance.layout = self.cleaned_data['layout']
            return super().save(commit=commit)
