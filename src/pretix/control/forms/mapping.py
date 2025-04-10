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
import json

from django import forms
from django.forms import formset_factory
from django.utils.translation import gettext_lazy as _

from pretix.base.datasync.datasync import (
    MODE_APPEND_LIST, MODE_OVERWRITE, MODE_SET_IF_EMPTY, MODE_SET_IF_NEW,
)
from pretix.base.datasync.sourcefields import QUESTION_TYPE_IDENTIFIERS


class PropertyMappingForm(forms.Form):
    pretix_field = forms.CharField()
    external_field = forms.CharField()
    value_map = forms.CharField(required=False)
    overwrite = forms.ChoiceField(
        choices=[
            (MODE_OVERWRITE, _("Overwrite")),
            (MODE_SET_IF_NEW, _("Fill if new contact")),
            (MODE_SET_IF_EMPTY, _("Fill if empty")),
            (MODE_APPEND_LIST, _("Add to list")),
        ]
    )

    def __init__(self, pretix_fields, external_fields_id, available_modes, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pretix_field"] = forms.ChoiceField(
            label=_("pretix Field"),
            choices=pretix_fields_choices(pretix_fields, kwargs.get("initial", {}).get("pretix_field")),
            required=False,
        )
        if external_fields_id:
            self.fields["external_field"] = forms.ChoiceField(
                widget=forms.Select(
                    attrs={
                        "data-model-select2": "json_script",
                        "data-select2-src": "#" + external_fields_id,
                    },
                ),
            )
            self.fields["external_field"].choices = [
                (self["external_field"].value(), self["external_field"].value()),
            ]
        self.fields["overwrite"].choices = [
            (key, label) for (key, label) in self.fields["overwrite"].choices if key in available_modes
        ]


class PropertyMappingFormSet(formset_factory(
    PropertyMappingForm,
    can_order=True,
    can_delete=True,
    extra=0,
)):
    template_name = "pretixcontrol/datasync/property_mapping_formset.html"

    def __init__(self, pretix_fields, external_fields, available_modes, prefix, *args, initial_json=None, **kwargs):
        if initial_json:
            kwargs["initial"] = json.loads(initial_json)
        super().__init__(
            form_kwargs={
                "pretix_fields": pretix_fields,
                "external_fields_id": prefix + "external-fields" if external_fields else None,
                "available_modes": available_modes,
            },
            prefix=prefix,
            *args, **kwargs)
        self.external_fields = external_fields

    def get_context(self):
        ctx = super().get_context()
        ctx["external_fields"] = self.external_fields
        ctx["external_fields_id"] = self.prefix + "external-fields"
        return ctx

    def to_property_mapping_json(self):
        mappings = [f.cleaned_data for f in self.ordered_forms]
        return json.dumps(mappings)


def pretix_fields_choices(pretix_fields, initial_choice):
    return [
        (f.key, f.label + " [" + QUESTION_TYPE_IDENTIFIERS[f.type] + "]")
        for f in pretix_fields
        if not f.deprecated or f.key == initial_choice
    ]
