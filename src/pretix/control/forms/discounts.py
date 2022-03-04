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
from django.utils.translation import ugettext_lazy as _

from pretix.base.channels import get_all_sales_channels
from pretix.base.forms import I18nModelForm
from pretix.base.forms.widgets import SplitDateTimePickerWidget
from pretix.base.models import Discount
from pretix.control.forms import ItemMultipleChoiceField, SplitDateTimeField


class DiscountForm(I18nModelForm):
    class Meta:
        model = Discount
        localized_fields = '__all__'
        fields = [
            'internal_name',
            'sales_channels',
            'available_from',
            'available_until',
            'subevent_mode',
            'condition_all_products',
            'condition_limit_products',
            'condition_min_count',
            'condition_min_value',
            'condition_apply_to_addons',
            'benefit_discount_matching_percent',
            'benefit_only_apply_to_cheapest_n_matches',
        ]
        field_classes = {
            'available_from': SplitDateTimeField,
            'available_until': SplitDateTimeField,
            'condition_limit_products': ItemMultipleChoiceField,
        }
        widgets = {
            'subevent_mode': forms.RadioSelect,
            'available_from': SplitDateTimePickerWidget(),
            'available_until': SplitDateTimePickerWidget(attrs={'data-date-after': '#id_available_from_0'}),
            'condition_limit_products': forms.CheckboxSelectMultiple(attrs={
                'data-inverse-dependency': '<[name$=all_products]',
                'class': 'scrolling-multiple-choice',
            }),
        }

    def __init__(self, *args, **kwargs):
        self.event = kwargs['event']
        super().__init__(*args, **kwargs)

        self.fields['sales_channels'] = forms.MultipleChoiceField(
            label=_('Sales channels'),
            required=True,
            choices=(
                (c.identifier, c.verbose_name) for c in get_all_sales_channels().values()
                if c.discounts_supported
            ),
            widget=forms.CheckboxSelectMultiple,
        )
        self.fields['condition_limit_products'].queryset = self.event.items.all()

        if not self.event.has_subevents:
            del self.fields['subevent_mode']
