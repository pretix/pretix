import re

from django.core.exceptions import ValidationError
from django.core.validators import BaseValidator
from django.utils.deconstruct import deconstructible
from django.utils.translation import ugettext_lazy as _
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

        data_placeholders = list(re.findall(r'({[\w\s]*})', value, re.X))
        invalid_placeholders = []
        for placeholder in data_placeholders:
            if placeholder not in self.limit_value:
                invalid_placeholders.append(placeholder)
        if invalid_placeholders:
            raise ValidationError(
                _('Invalid placeholder(s): %(value)s'),
                code='invalid',
                params={'value': ", ".join(invalid_placeholders,)})

    def clean(self, x):
        return x


class BlacklistValidator:

    blacklist = []

    def __call__(self, value):
        # Validation logic
        if value in self.blacklist:
            raise ValidationError(
                _('This slug has an invalid value: %(value)s.'),
                code='invalid',
                params={'value': value},
            )


@deconstructible
class EventSlugBlacklistValidator(BlacklistValidator):

    blacklist = [
        'download',
        'healthcheck',
        'locale',
        'control',
        'redirect',
        'jsi18n',
        'metrics',
        '_global',
        '__debug__',
        'api',
        'events',
        'csp_report',
    ]


@deconstructible
class OrganizerSlugBlacklistValidator(BlacklistValidator):

    blacklist = [
        'download',
        'healthcheck',
        'locale',
        'control',
        'pretixdroid',
        'redirect',
        'jsi18n',
        'metrics',
        '_global',
        '__debug__',
        'about',
        'api',
        'csp_report',
    ]
