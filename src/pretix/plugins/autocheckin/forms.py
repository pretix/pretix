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
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django_scopes.forms import (
    SafeModelChoiceField, SafeModelMultipleChoiceField,
)

from pretix.base.models import ItemVariation
from pretix.control.forms import SalesChannelCheckboxSelectMultiple
from pretix.control.forms.widgets import Select2
from pretix.plugins.autocheckin.models import AutoCheckinRule

from pretix.base.services.placeholders import FormPlaceholderMixin  # noqa


class AutoCheckinRuleForm(forms.ModelForm):
    itemvars = forms.MultipleChoiceField(
        label=_("Products"),
        required=False,
    )
    limit_payment_methods = forms.MultipleChoiceField(
        label=_("Only including usage of payment providers"),
        choices=[],
        required=False,
        widget=forms.RadioSelect,
    )

    class Meta:
        model = AutoCheckinRule

        fields = [
            "list",
            "mode",
            "all_sales_channels",
            "limit_sales_channels",
            "all_products",
            "all_payment_methods",
        ]
        field_classes = {
            "mode": forms.RadioSelect,
            "list": SafeModelChoiceField,
            "limit_sales_channels": SafeModelMultipleChoiceField,
        }

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop("event")
        self.instance = kwargs.get("instance", None)

        initial = kwargs.get("initial", {})
        if self.instance and self.instance.pk and "itemvars" not in initial:
            initial["itemvars"] = [
                str(i.pk) for i in self.instance.limit_products.all()
            ] + [
                "{}-{}".format(v.item_id, v.pk)
                for v in self.instance.limit_variations.all()
            ]
        if (
            self.instance
            and self.instance.pk
            and "limit_payment_methods" not in initial
        ):
            initial["limit_payment_methods"] = self.instance.limit_payment_methods
        kwargs["initial"] = initial

        super().__init__(*args, **kwargs)

        self.fields["limit_sales_channels"].queryset = (
            self.event.organizer.sales_channels.all()
        )
        self.fields["limit_sales_channels"].widget = SalesChannelCheckboxSelectMultiple(
            self.event,
            attrs={
                "data-inverse-dependency": "<[name$=all_sales_channels]",
                "class": "scrolling-multiple-choice",
            },
            choices=self.fields["limit_sales_channels"].widget.choices,
        )

        choices = []
        for item in self.event.items.all():
            if len(item.variations.all()) > 0:
                allvars = _("All variations")
                choices.append(
                    (
                        "{}".format(item.pk),
                        (
                            f"{item} – {allvars}"
                            if item.active
                            else mark_safe(
                                f'<strike class="text-muted">{escape(item)} – {allvars}</strike>'
                            )
                        ),
                    )
                )
            else:
                choices.append(
                    (
                        "{}".format(item.pk),
                        (
                            str(item)
                            if item.active
                            else mark_safe(
                                f'<strike class="text-muted">{escape(item)}</strike>'
                            )
                        ),
                    )
                )
            for v in item.variations.all():
                choices.append(
                    (
                        "{}-{}".format(item.pk, v.pk),
                        (
                            "{} – {}".format(item, v.value)
                            if item.active
                            else mark_safe(
                                f'<strike class="text-muted">{escape(item)} – {escape(v.value)}</strike>'
                            )
                        ),
                    )
                )

        self.fields["itemvars"].widget = forms.CheckboxSelectMultiple(
            attrs={
                "data-inverse-dependency": "<[name$=all_products]",
                "class": "scrolling-multiple-choice",
            },
        )
        self.fields["itemvars"].choices = choices

        self.fields["list"].queryset = self.event.checkin_lists.all()
        self.fields["list"].widget = Select2(
            attrs={
                "data-model-select2": "generic",
                "data-select2-url": reverse(
                    "control:event.orders.checkinlists.select2",
                    kwargs={
                        "event": self.event.slug,
                        "organizer": self.event.organizer.slug,
                    },
                ),
            }
        )
        self.fields["list"].widget.choices = self.fields["list"].choices
        self.fields["list"].label = _("Check-in list")

        self.fields["list"].widget.choices = self.fields["list"].choices

        self.fields["limit_payment_methods"].choices += [
            (p.identifier, p.verbose_name)
            for p in self.event.get_payment_providers().values()
        ]
        self.fields["limit_payment_methods"].widget = forms.CheckboxSelectMultiple(
            attrs={
                "data-inverse-dependency": "<[name$=all_payment_methods]",
                "class": "scrolling-multiple-choice",
            },
            choices=self.fields["limit_payment_methods"].choices,
        )

    def save(self, *args, **kwargs):
        creating = not self.instance.pk

        self.instance.limit_payment_methods = (
            self.cleaned_data.get("limit_payment_methods") or []
        )

        inst = super().save(*args, **kwargs)

        selected_items = set(
            list(
                self.event.items.filter(
                    id__in=[i for i in self.cleaned_data["itemvars"] if "-" not in i]
                )
            )
        )
        selected_variations = list(
            ItemVariation.objects.filter(
                item__event=self.event,
                id__in=[
                    i.split("-")[1] for i in self.cleaned_data["itemvars"] if "-" in i
                ],
            )
        )

        current_items = [] if creating else self.instance.limit_products.all()
        current_variations = [] if creating else self.instance.limit_variations.all()

        self.instance.limit_products.remove(
            *[i for i in current_items if i not in selected_items]
        )
        self.instance.limit_products.add(
            *[i for i in selected_items if i not in current_items]
        )
        self.instance.limit_variations.remove(
            *[i for i in current_variations if i not in selected_variations]
        )
        self.instance.limit_variations.add(
            *[i for i in selected_variations if i not in current_variations]
        )
        return inst

    def clean(self):
        d = super().clean()

        if d["mode"] == AutoCheckinRule.MODE_PLACED and not d["all_payment_methods"]:
            raise ValidationError(
                {
                    "mode": _(
                        "When restricting by payment method, the rule should run after the payment was received."
                    )
                }
            )

        return d
