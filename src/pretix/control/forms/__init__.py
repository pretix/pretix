import os
from functools import partial
from itertools import product

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms import (
    BaseInlineFormSet, BaseModelFormSet, ModelForm, modelformset_factory,
)
from django.forms.widgets import flatatt
from django.utils.encoding import force_text
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _

from pretix.base.forms import I18nModelForm
from pretix.base.models import Item, ItemVariation


class I18nInlineFormSet(BaseInlineFormSet):
    """
    This is equivalent to a normal BaseInlineFormset, but cares for the special needs
    of I18nForms (see there for more information).
    """

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event', None)
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        kwargs['event'] = self.event
        return super()._construct_form(i, **kwargs)


class I18nFormSet(BaseModelFormSet):
    """
    This is equivalent to a normal BaseModelFormset, but cares for the special needs
    of I18nForms (see there for more information).
    """

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event', None)
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        kwargs['event'] = self.event
        return super()._construct_form(i, **kwargs)

    @property
    def empty_form(self):
        form = self.form(
            auto_id=self.auto_id,
            prefix=self.add_prefix('__prefix__'),
            empty_permitted=True,
            event=self.event
        )
        self.add_fields(form, None)
        return form


class TolerantFormsetModelForm(I18nModelForm):
    """
    This is equivalent to a normal I18nModelForm, but works around a problem that
    arises when the form is used inside a FormSet with can_order=True and django-formset-js
    enabled. In this configuration, even empty "extra" forms might have an ORDER value
    sent and Django marks the form as empty and raises validation errors because the other
    fields have not been filled.
    """

    def has_changed(self) -> bool:
        """
        Returns True if data differs from initial. Contrary to the default
        implementation, the ORDER field is being ignored.
        """
        for name, field in self.fields.items():
            if name == 'ORDER' or name == 'id':
                continue
            prefixed_name = self.add_prefix(name)
            data_value = field.widget.value_from_datadict(self.data, self.files, prefixed_name)
            if not field.show_hidden_initial:
                initial_value = self.initial.get(name, field.initial)
                if callable(initial_value):
                    initial_value = initial_value()
            else:
                initial_prefixed_name = self.add_initial_prefix(name)
                hidden_widget = field.hidden_widget()
                try:
                    initial_value = field.to_python(hidden_widget.value_from_datadict(
                        self.data, self.files, initial_prefixed_name))
                except forms.ValidationError:
                    # Always assume data has changed if validation fails.
                    self._changed_data.append(name)
                    continue
            # We're using a private API of Django here. This is not nice, but no problem as it seems
            # like this will become a public API in future Django.
            if field._has_changed(initial_value, data_value):
                return True
        return False


def selector(values, prop):
    # Given an iterable of PropertyValue objects, this will return a
    # list of their primary keys, ordered by the primary keys of the
    # properties they belong to EXCEPT the value for the property prop2.
    # We'll see later why we need this.
    return [
        v.id for v in sorted(values, key=lambda v: v.prop.id)
        if v.prop.id != prop.id
    ]


class ExtFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        ext_whitelist = kwargs.pop("ext_whitelist")
        self.ext_whitelist = [i.lower() for i in ext_whitelist]
        super().__init__(*args, **kwargs)

    def clean(self, *args, **kwargs):
        data = super().clean(*args, **kwargs)
        if data:
            filename = data.name
            ext = os.path.splitext(filename)[1]
            ext = ext.lower()
            if ext not in self.ext_whitelist:
                raise forms.ValidationError(_("Filetype not allowed!"))
        return data
