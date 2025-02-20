import json
from django import forms
from django.forms import ModelForm
from django.utils.translation import gettext_lazy as _
from pretix.base.forms import SettingsForm


MODE_OVERWRITE = "overwrite"
MODE_SET_IF_NEW = "if_new"
MODE_SET_IF_EMPTY = "if_empty"
MODE_APPEND_LIST = "append"


class PropertyMappingForm(forms.Form):
    pretix_field = forms.CharField()
    external_field = forms.ChoiceField(
        widget=forms.Select(
            attrs={
                "data-model-select2": "json_script",
                "data-select2-src": "#contact-props",
            }
        )
    )
    value_map = forms.CharField(required=False)
    overwrite = forms.ChoiceField(
        choices=[
            (MODE_OVERWRITE, _("Overwrite")),
            (MODE_SET_IF_NEW, _("Fill if new contact")),
            (MODE_SET_IF_EMPTY, _("Fill if empty")),
            (MODE_APPEND_LIST, _("Add to list")),
        ]
    )

    def __init__(self, pretix_fields, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pretix_field"] = forms.ChoiceField(
            label=_("pretix Field"),
            choices=pretix_fields_choices(pretix_fields),
            required=False,
        )
        self.fields["external_field"].choices = [
            (self["external_field"].value(), self["external_field"].value())
        ]


def pretix_fields_choices(pretix_fields):
    return [
        (key, label + " [" + ptype.value + "]")
        for (required_input, key, label, ptype, enum_opts, getter) in pretix_fields
    ]
