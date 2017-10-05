import os

from django import forms
from django.utils.formats import get_format
from django.utils.html import conditional_escape
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from ...base.forms import I18nModelForm


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


class ClearableBasenameFileInput(forms.ClearableFileInput):

    def get_template_substitution_values(self, value):
        """
        Return value-related substitutions.
        """
        bname = os.path.basename(value.name)
        return {
            'initial': conditional_escape(bname),
            'initial_url': conditional_escape(value.url),
        }


class ExtFileField(forms.FileField):
    widget = ClearableBasenameFileInput

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


class SlugWidget(forms.TextInput):
    template_name = 'pretixcontrol/slug_widget.html'
    prefix = ''

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        ctx['pre'] = self.prefix
        return ctx


class SplitDateTimePickerWidget(forms.SplitDateTimeWidget):

    def __init__(self, attrs=None, date_format=None, time_format=None):
        attrs = attrs or {}
        if 'placeholder' in attrs:
            del attrs['placeholder']
        date_attrs = dict(attrs)
        time_attrs = dict(attrs)
        date_attrs.setdefault('class', 'form-control splitdatetimepart')
        time_attrs.setdefault('class', 'form-control splitdatetimepart')
        date_attrs['class'] += ' datepickerfield'
        time_attrs['class'] += ' timepickerfield'
        time_attrs['class'] += ' timepickerfield'

        df = date_format or get_format('DATE_INPUT_FORMATS')[0]
        date_attrs['placeholder'] = now().replace(
            year=2000, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        ).strftime(df)
        tf = time_format or get_format('TIME_INPUT_FORMATS')[0]
        time_attrs['placeholder'] = now().replace(
            year=2000, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        ).strftime(tf)

        widgets = (
            forms.DateInput(attrs=date_attrs, format=date_format),
            forms.TimeInput(attrs=time_attrs, format=time_format),
        )
        # Skip one hierarchy level
        forms.MultiWidget.__init__(self, widgets, attrs)
