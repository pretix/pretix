from django import forms
from django.forms import formset_factory
from django.utils.translation import gettext_lazy as _

from pretix.base.datasync.sourcefields import QUESTION_TYPE_IDENTIFIERS
from pretix.base.datasync.datasync import MODE_SET_IF_NEW, MODE_SET_IF_EMPTY, MODE_OVERWRITE, MODE_APPEND_LIST

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

    def __init__(self, pretix_fields, external_fields_id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pretix_field"] = forms.ChoiceField(
            label=_("pretix Field"),
            choices=pretix_fields_choices(pretix_fields),
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
        print(self.fields)


class PropertyMappingFormSet(formset_factory(
    PropertyMappingForm,
    can_order=True,
    can_delete=True,
    extra=0,
)):
    template_name = "pretixcontrol/datasync/property_mapping_formset.html"

    def __init__(self, pretix_fields, external_fields, prefix, *args, **kwargs):
        super().__init__(
            form_kwargs={
                "pretix_fields": pretix_fields,
                "external_fields_id": prefix + "external-fields" if external_fields else None,
            },
            prefix=prefix,
            *args, **kwargs)
        self.external_fields = external_fields

    def get_context(self):
        ctx = super().get_context()
        ctx["external_fields"] = self.external_fields
        ctx["external_fields_id"] = self.prefix + "external-fields"
        return ctx


def pretix_fields_choices(pretix_fields):
    return [
        (key, label + " [" + QUESTION_TYPE_IDENTIFIERS[ptype] + "]")
        for (required_input, key, label, ptype, enum_opts, getter) in pretix_fields
    ]
