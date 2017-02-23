import copy
import json
from contextlib import contextmanager
from typing import Dict, List, Optional, Union

from django import forms
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Model, QuerySet, TextField
from django.utils import translation
from django.utils.formats import date_format, number_format
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext


class LazyI18nString:
    """
    This represents an internationalized string that is/was/will be stored in the database.
    """

    def __init__(self, data: Optional[Union[str, Dict[str, str]]]):
        """
        Creates a new i18n-aware string.

        :param data: If this is a dictionary, it is expected to map language codes to translations.
            If this is a string that can be parsed as JSON, it will be parsed and used as such a dictionary.
            If this is anything else, it will be cast to a string and used for all languages.
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

        If no string is available in the currently active language, this will give you
        the string in the system's default language. If this is unavailable as well, it
        will give you the string in the first language available.
        """
        return self.localize(translation.get_language() or settings.LANGUAGE_CODE)

    def __bool__(self):
        if not self.data:
            return False
        if isinstance(self.data, dict):
            return any(self.data.values())
        return True

    def localize(self, lng: str) -> str:
        """
        Evaluate the given string with respect to the locale defined by ``lng``.

        If no string is available in the currently active language, this will give you
        the string in the system's default language. If this is unavailable as well, it
        will give you the string in the first language available.

        :param lng: A locale code, e.g. ``de``. If you specify a code including a country
            or region like ``de-AT``, exact matches will be used preferably, but if only
            a ``de`` or ``de-AT`` translation exists, this might be returned as well.
        """
        if self.data is None:
            return ""

        if isinstance(self.data, dict):
            firstpart = lng.split('-')[0]
            similar = [l for l in self.data.keys() if (l.startswith(firstpart + "-") or firstpart == l) and l != lng]
            if self.data.get(lng):
                return self.data[lng]
            elif self.data.get(firstpart):
                return self.data[firstpart]
            elif similar and any([self.data.get(s) for s in similar]):
                for s in similar:
                    if self.data.get(s):
                        return self.data.get(s)
            elif self.data.get(settings.LANGUAGE_CODE):
                return self.data[settings.LANGUAGE_CODE]
            elif len(self.data):
                return list(self.data.items())[0][1]
            else:
                return ""
        else:
            return str(self.data)

    def __repr__(self) -> str:  # NOQA
        return '<LazyI18nString: %s>' % repr(self.data)

    def __lt__(self, other) -> bool:  # NOQA
        return str(self) < str(other)

    def __format__(self, format_spec):
        return self.__str__()

    def __eq__(self, other):
        if other is None:
            return False
        if hasattr(other, 'data'):
            return self.data == other.data
        return self.data == other

    class LazyGettextProxy:
        def __init__(self, lazygettext):
            self.lazygettext = lazygettext

        def __getitem__(self, item):
            with language(item):
                return str(ugettext(self.lazygettext))

        def __contains__(self, item):
            return True

        def __str__(self):
            return str(ugettext(self.lazygettext))

    @classmethod
    def from_gettext(cls, lazygettext):
        l = LazyI18nString({})
        l.data = cls.LazyGettextProxy(lazygettext)
        return l


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
            a['lang'] = lng
            widgets.append(self.widget(attrs=a))
        super().__init__(widgets, attrs)

    def decompress(self, value):
        data = []
        first_enabled = None
        any_filled = False
        any_enabled_filled = False
        if not isinstance(value, LazyI18nString):
            value = LazyI18nString(value)
        for i, lng in enumerate(self.langcodes):
            dataline = (
                value.data[lng]
                if value is not None and (
                    isinstance(value.data, dict) or isinstance(value.data, LazyI18nString.LazyGettextProxy)
                ) and lng in value.data
                else None
            )
            any_filled = any_filled or (lng in self.enabled_langcodes and dataline)
            if not first_enabled and lng in self.enabled_langcodes:
                first_enabled = i
                if dataline:
                    any_enabled_filled = True
            data.append(dataline)
        if value and not isinstance(value.data, dict):
            data[first_enabled] = value.data
        elif value and not any_enabled_filled:
            data[first_enabled] = value.localize(self.enabled_langcodes[0])
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
                final_attrs = dict(
                    final_attrs,
                    id='%s_%s' % (id_, i),
                    title=self.langcodes[i]
                )
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

    It contains special treatment to make sure that a field marked as "required" is validated
    as "filled out correctly" if *at least one* translation is filled it. It is never required
    to fill in all of them. This has the drawback that the HTML property ``required`` is set on
    none of the fields as this would lead to irritating behaviour.

    :param langcodes: An iterable of locale codes that the widget should render a field for. If
        omitted, fields will be rendered for all languages supported by pretix.
    """

    def compress(self, data_list):
        langcodes = self.langcodes
        data = {}
        for i, value in enumerate(data_list):
            data[langcodes[i]] = value
        return LazyI18nString(data)

    def clean(self, value):
        if isinstance(value, LazyI18nString):
            # This happens e.g. if the field is disabled
            return value
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
        self.one_required = kwargs.get('required', True)
        kwargs['required'] = False
        kwargs['widget'] = kwargs['widget'](
            langcodes=self.langcodes, field=self, **kwargs.pop('widget_kwargs', {})
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


class LazyDate:
    def __init__(self, value):
        self.value = value

    def __format__(self, format_spec):
        return self.__str__()

    def __str__(self):
        return date_format(self.value, "SHORT_DATE_FORMAT")


class LazyNumber:
    def __init__(self, value, decimal_pos=2):
        self.value = value
        self.decimal_pos = decimal_pos

    def __format__(self, format_spec):
        return self.__str__()

    def __str__(self):
        return number_format(self.value, decimal_pos=self.decimal_pos)


@contextmanager
def language(lng):
    _lng = translation.get_language()
    translation.activate(lng or settings.LANGUAGE_CODE)
    try:
        yield
    finally:
        translation.activate(_lng)


class LazyLocaleException(Exception):
    def __init__(self, msg, msgargs=None):
        self.msg = msg
        self.msgargs = msgargs
        super().__init__(msg, msgargs)

    def __str__(self):
        if self.msgargs:
            return ugettext(self.msg) % self.msgargs
        else:
            return ugettext(self.msg)
