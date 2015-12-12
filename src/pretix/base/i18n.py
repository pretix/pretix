import copy
import json

from django import forms
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Model, QuerySet, TextField
from django.utils import translation
from django.utils.safestring import mark_safe
from typing import Dict, List


class LazyI18nString:
    """
    This represents an internationalized string that is/was/will be stored in the database.
    """

    def __init__(self, data: Dict[str, str]):
        """
        Input data should be a dictionary which maps language codes to content.
        """
        self.data = data
        if isinstance(self.data, str) and self.data is not None:
            try:
                j = json.loads(self.data)
            except ValueError:
                pass
            else:
                self.data = j

    def __str__(self) -> str:
        """
        Evaluate the given string with respect to the currently active locale.
        This will rather return you a string in a wrong language than give you an
        empty value.
        """
        if self.data is None:
            return ""
        if isinstance(self.data, dict):
            lng = translation.get_language()
            firstpart = lng.split('-')[0]
            similar = [l for l in self.data.keys() if l.startswith(firstpart + "-")]
            if lng in self.data and self.data[lng]:
                return self.data[lng]
            elif firstpart in self.data:
                return self.data[firstpart]
            elif similar:
                return self.data[similar[0]]
            elif settings.LANGUAGE_CODE in self.data and self.data[settings.LANGUAGE_CODE]:
                return self.data[settings.LANGUAGE_CODE]
            elif len(self.data):
                return list(self.data.items())[0][1]
            else:
                return ""
        else:
            return str(self.data)

    def __repr__(self) -> str:
        return '<LazyI18nString: %s>' % repr(self.data)

    def __lt__(self, other) -> bool:  # NOQA
        return str(self) < str(other)


class I18nWidget(forms.MultiWidget):
    """
    The default form widget for I18nCharField and I18nTextField. It makes
    use of Django's MultiWidget mechanism and does some magic to save you
    time.
    """
    widget = forms.TextInput

    def __init__(self, langcodes: List[str], field: forms.Field, attrs=None):
        widgets = []
        self.langcodes = langcodes
        self.enabled_langcodes = langcodes
        self.field = field
        for lng in self.langcodes:
            a = copy.copy(attrs) or {}
            a['data-lang'] = lng
            widgets.append(self.widget(attrs=a))
        super().__init__(widgets, attrs)

    def decompress(self, value):
        data = []
        if not isinstance(value, LazyI18nString):
            value = LazyI18nString(value)
        for lng in self.langcodes:
            data.append(
                value.data[lng]
                if value is not None and isinstance(value.data, dict) and lng in value.data
                else None
            )
        if value and not isinstance(value.data, dict):
            data[0] = value.data
        return data

    def render(self, name, value, attrs=None):
        if self.is_localized:
            for widget in self.widgets:
                widget.is_localized = self.is_localized
        # value is a list of values, each corresponding to a widget
        # in self.widgets.
        if not isinstance(value, list):
            value = self.decompress(value)
        output = []
        final_attrs = self.build_attrs(attrs)
        id_ = final_attrs.get('id', None)
        for i, widget in enumerate(self.widgets):
            if self.langcodes[i] not in self.enabled_langcodes:
                continue
            try:
                widget_value = value[i]
            except IndexError:
                widget_value = None
            if id_:
                final_attrs = dict(final_attrs, id='%s_%s' % (id_, i))
            output.append(widget.render(name + '_%s' % i, widget_value, final_attrs))
        return mark_safe(self.format_output(output))

    def format_output(self, rendered_widgets):
        return '<div class="i18n-form-group">%s</div>' % super().format_output(rendered_widgets)


class I18nTextInput(I18nWidget):
    widget = forms.TextInput


class I18nTextarea(I18nWidget):
    widget = forms.Textarea


class I18nFormField(forms.MultiValueField):
    """
    The form field that is used by I18nCharField and I18nTextField. It makes use
    of Django's MultiValueField mechanism to create one sub-field per available
    language.
    """

    def compress(self, data_list):
        langcodes = self.langcodes
        data = {}
        for i, value in enumerate(data_list):
            data[langcodes[i]] = value
        return LazyI18nString(data)

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
        self.langcodes = kwargs.pop('langcodes', [l[0] for l in settings.LANGUAGES])
        self.one_required = kwargs['required']
        kwargs['required'] = False
        kwargs['widget'] = kwargs['widget'](
            langcodes=self.langcodes, field=self
        )
        defaults.update(**kwargs)
        for lngcode in self.langcodes:
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
        if isinstance(value, LazyI18nString):
            return value
        return LazyI18nString(value)

    def get_prep_value(self, value):
        if isinstance(value, LazyI18nString):
            value = value.data
        if isinstance(value, dict):
            return json.dumps({k: v for k, v in value.items() if v}, sort_keys=True)
        return value

    def get_prep_lookup(self, lookup_type, value):  # NOQA
        raise TypeError('Lookups on i18n string currently not supported.')

    def from_db_value(self, value, expression, connection, context):
        return LazyI18nString(value)

    def formfield(self, **kwargs):
        defaults = {'form_class': self.form_class, 'widget': self.widget}
        defaults.update(kwargs)
        return super().formfield(**defaults)


class I18nCharField(I18nFieldMixin, TextField):
    """
    A CharField which takes internationalized data. Internally, a TextField dabase
    field is used to store JSON. If you interact with this field, you will work
    with LazyI18nString instances.
    """
    widget = I18nTextInput


class I18nTextField(I18nFieldMixin, TextField):
    """
    Like I18nCharField, but for TextFields.
    """
    widget = I18nTextarea


class I18nJSONEncoder(DjangoJSONEncoder):
    def default(self, obj):
        if isinstance(obj, LazyI18nString):
            return obj.data
        elif isinstance(obj, QuerySet):
            return list(obj)
        elif isinstance(obj, Model):
            return {'type': obj.__class__.__name__, 'id': obj.id}
        else:
            return super().default(obj)
