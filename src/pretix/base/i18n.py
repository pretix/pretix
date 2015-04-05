import copy
import json
from django.conf import settings
from django.db.models import TextField, SubfieldBase
from django import forms
from django.utils import translation


class LazyI18String:
    def __init__(self, data):
        self.data = data
        if isinstance(self.data, str) and self.data is not None:
            try:
                j = json.loads(self.data)
            except ValueError:
                pass
            else:
                self.data = j

    def __str__(self):
        if self.data is None:
            return ""
        if isinstance(self.data, dict):
            lng = translation.get_language()
            if lng in self.data and self.data[lng]:
                return self.data[lng]
            elif settings.LANGUAGE_CODE in self.data and self.data[settings.LANGUAGE_CODE]:
                return self.data[settings.LANGUAGE_CODE]
            elif len(self.data):
                return self.data.items()[0][1]
            else:
                return ""
        else:
            return str(self.data)

    def __repr__(self):
        return '<LazyI18nString: %s>' % repr(self.data)

    def __lt__(self, other):
        return str(self) < str(other)


class I18nWidget(forms.MultiWidget):
    widget = forms.TextInput

    def langcodes(self):
        return [l[0] for l in settings.LANGUAGES]

    def __init__(self, attrs=None):
        widgets = []
        for lng in self.langcodes():
            a = copy.copy(attrs) or {}
            a['data-lang'] = lng
            widgets.append(self.widget(attrs=a))
        super().__init__(widgets, attrs)

    def decompress(self, value):
        data = []
        for lng in self.langcodes():
            data.append(
                value.data[lng]
                if value is not None and isinstance(value.data, dict) and lng in value.data
                else None
            )
        if not isinstance(value.data, dict):
            data[0] = value.data
        return data

    def format_output(self, rendered_widgets):
        return '<div class="i18n-form-group">%s</div>' % super().format_output(rendered_widgets)


class I18nTextInput(I18nWidget):
    widget = forms.TextInput


class I18nTextarea(I18nWidget):
    widget = forms.Textarea


class I18nFormField(forms.MultiValueField):

    def compress(self, data_list):
        langcodes = self.langcodes()
        data = {}
        for i, value in enumerate(data_list):
            data[langcodes[i]] = value
        return LazyI18String(data)

    def langcodes(self):
        return [l[0] for l in settings.LANGUAGES]

    def clean(self, value):
        found = False
        clean_data = []
        errors = []
        for i, field in enumerate(self.fields):
            try:
                field_value = value[i]
            except IndexError:
                field_value = None
            if field_value not in self.empty_values:
                found = True
            try:
                clean_data.append(field.clean(field_value))
            except forms.ValidationError as e:
                # Collect all validation errors in a single list, which we'll
                # raise at the end of clean(), rather than raising a single
                # exception for the first error we encounter. Skip duplicates.
                errors.extend(m for m in e.error_list if m not in errors)
        if errors:
            raise forms.ValidationError(errors)
        if self.one_required and not found:
            raise forms.ValidationError(self.error_messages['required'], code='required')

        out = self.compress(clean_data)
        self.validate(out)
        self.run_validators(out)
        return out

    def __init__(self, *args, **kwargs):
        fields = []
        defaults = {
            'widget': self.widget,
            'max_length': kwargs.pop('max_length', None),
        }
        self.one_required = kwargs['required']
        kwargs['required'] = False
        defaults.update(**kwargs)
        for lngcode in self.langcodes():
            defaults['label'] = '%s (%s)' % (defaults.get('label'), lngcode)
            fields.append(forms.CharField(**defaults))
        super().__init__(
            fields=fields, require_all_fields=False, *args, **kwargs
        )


class I18nFieldMixin:
    form_class = I18nFormField
    widget = I18nTextInput

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event', None)
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if isinstance(value, LazyI18String):
            return value
        return LazyI18String(value)

    def get_prep_value(self, value):
        if isinstance(value, LazyI18String):
            value = value.data
        if isinstance(value, dict):
            return json.dumps(value, sort_keys=True)
        return value

    def get_prep_lookup(self, lookup_type, value):
        raise TypeError('Lookups on i18n string currently not supported.')

    def formfield(self, **kwargs):
        defaults = {'form_class': self.form_class, 'widget': self.widget}
        defaults.update(kwargs)
        return super().formfield(**defaults)


class I18nCharField(I18nFieldMixin, TextField, metaclass=SubfieldBase):
    widget = I18nTextInput


class I18nTextField(I18nFieldMixin, TextField, metaclass=SubfieldBase):
    widget = I18nTextarea
