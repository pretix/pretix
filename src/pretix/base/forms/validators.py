import re

from django.core.exceptions import ValidationError
from django.core.validators import BaseValidator
from django.utils.translation import gettext_lazy as _
from i18nfield.strings import LazyI18nString


class PlaceholderValidator(BaseValidator):
    """
    Takes list of allowed placeholders,
    validates form field by checking for placeholders,
    which are not presented in taken list.
    """

    def __init__(self, limit_value):
        super().__init__(limit_value)
        self.limit_value = limit_value

    def __call__(self, value):
        if isinstance(value, LazyI18nString):
            for l, v in value.data.items():
                self.__call__(v)
            return

        if value.count('{') != value.count('}'):
            raise ValidationError(
                _('Invalid placeholder syntax: You used a different number of "{" than of "}".'),
                code='invalid_placeholder_syntax',
            )

        data_placeholders = list(re.findall(r'({[^}]*})', value, re.X))
        invalid_placeholders = []
        for placeholder in data_placeholders:
            if placeholder not in self.limit_value:
                invalid_placeholders.append(placeholder)
        if invalid_placeholders:
            raise ValidationError(
                _('Invalid placeholder(s): %(value)s'),
                code='invalid_placeholders',
                params={'value': ", ".join(invalid_placeholders,)})

    def clean(self, x):
        return x
