from django.core import exceptions
from django.db.models import TextField, lookups as builtin_lookups
from django.utils.translation import gettext_lazy as _

DELIMITER = "\x1F"


class MultiStringField(TextField):
    default_error_messages = {
        'delimiter_found': _('No value can contain the delimiter character.')
    }

    def __init__(self, verbose_name=None, name=None, **kwargs):
        super().__init__(verbose_name, name, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return name, path, args, kwargs

    def to_python(self, value):
        if isinstance(value, (list, tuple)):
            return value
        elif value:
            return value.split(DELIMITER)
        else:
            return []

    def get_prep_value(self, value):
        if isinstance(value, (list, tuple)):
            return DELIMITER + DELIMITER.join(value) + DELIMITER
        elif value is None:
            return ""
        raise TypeError("Invalid data type passed.")

    def get_prep_lookup(self, lookup_type, value):  # NOQA
        raise TypeError('Lookups on multi strings are currently not supported.')

    def from_db_value(self, value, expression, connection, context):
        if value:
            return value.split(DELIMITER)
        else:
            return []

    def validate(self, value, model_instance):
        super().validate(value, model_instance)
        for l in value:
            if DELIMITER in l:
                raise exceptions.ValidationError(
                    self.error_messages['delimiter_found'],
                    code='delimiter_found',
                )

    def get_lookup(self, lookup_name):
        if lookup_name == 'contains':
            return MultiStringContains
        elif lookup_name == 'icontains':
            return MultiStringIContains
        raise NotImplementedError(
            "Lookup '{}' doesn't work with MultiStringField".format(lookup_name),
        )


class MultiStringContains(builtin_lookups.Contains):
    def process_rhs(self, qn, connection):
        sql, params = super().process_rhs(qn, connection)
        params[0] = "%" + DELIMITER + params[0][1:-1] + DELIMITER + "%"
        return sql, params


class MultiStringIContains(builtin_lookups.IContains):
    def process_rhs(self, qn, connection):
        sql, params = super().process_rhs(qn, connection)
        params[0] = "%" + DELIMITER + params[0][1:-1] + DELIMITER + "%"
        return sql, params
