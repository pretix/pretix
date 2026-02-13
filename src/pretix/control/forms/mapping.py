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
from itertools import groupby

from django import forms
from django.forms import formset_factory
from django.utils.translation import gettext_lazy as _

from pretix.base.models import Question
from pretix.base.models.datasync import (
    MODE_APPEND_LIST, MODE_OVERWRITE, MODE_SET_IF_EMPTY, MODE_SET_IF_NEW,
)


class PropertyMappingForm(forms.Form):
    pretix_field = forms.CharField()
    external_field = forms.CharField()
    value_map = forms.CharField(required=False)
    overwrite = forms.ChoiceField(
        choices=[
            (MODE_OVERWRITE, _("Overwrite")),
            (MODE_SET_IF_NEW, _("Fill if new")),
            (MODE_SET_IF_EMPTY, _("Fill if empty")),
            (MODE_APPEND_LIST, _("Add to list")),
        ]
    )

    def __init__(self, pretix_fields, external_fields_id, available_modes, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pretix_field"] = forms.ChoiceField(
            label=_("pretix field"),
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
    template_name = "pretixcontrol/datasync/property_mappings_formset.html"

    def __init__(self, pretix_fields, external_fields, available_modes, prefix, *args, **kwargs):
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

    def to_property_mappings_list(self):
        """
        Returns a property mapping configuration as a JSON-serializable list of dictionaries.

        Each entry specifies how to transfer data from one pretix field to one field in the external system:

          - `pretix_field`: Name of a pretix data source field as declared in `pretix.base.datasync.sourcefields.get_data_fields`.
          - `external_field`: Name of the target field in the external system. Implementation-defined by the sync provider.
          - `value_map`: Dictionary mapping pretix value to external value. Only used for enumeration-type fields.
          - `overwrite`: Mode of operation if the object already exists in the target system.

            - `MODE_OVERWRITE` (`"overwrite"`) to always overwrite existing value.
            - `MODE_SET_IF_NEW` (`"if_new"`) to only set the value if object does not exist in target system yet.
            - `MODE_SET_IF_EMPTY` (`"if_empty"`) to only set the value if object does not exist in target system,
              or the field is currently empty in target system.
            - `MODE_APPEND_LIST` (`"append"`) if the field is an array or a multi-select: add the value to the list.
        """
        mappings = [f.cleaned_data for f in self.ordered_forms]
        return mappings


QUESTION_TYPE_LABELS = dict(Question.TYPE_CHOICES)


def pretix_fields_choices(pretix_fields, initial_choice):
    pretix_fields = sorted(pretix_fields, key=lambda f: f.category)
    grouped_fields = groupby(pretix_fields, lambda f: f.category)
    return [
        (f"{cat}", [
            (f.key, f.label + " [" + QUESTION_TYPE_LABELS[f.type] + "]")
            for f in fields
            if not f.deprecated or f.key == initial_choice
        ])
        for ((idx, cat), fields) in grouped_fields
    ]
