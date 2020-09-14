from contextlib import contextmanager

from django.conf import settings
from django.utils import translation
from django.utils.formats import date_format, number_format
from django.utils.translation import gettext

from pretix.base.templatetags.money import money_filter

from i18nfield.fields import (  # noqa
    I18nCharField, I18nTextarea, I18nTextField, I18nTextInput,
)
from i18nfield.forms import I18nFormField  # noqa
# Compatibility imports
from i18nfield.strings import LazyI18nString  # noqa
from i18nfield.utils import I18nJSONEncoder  # noqa


class LazyDate:
    def __init__(self, value):
        self.value = value

    def __format__(self, format_spec):
        return self.__str__()

    def __str__(self):
        return date_format(self.value, "SHORT_DATE_FORMAT")


class LazyExpiresDate:
    def __init__(self, expires):
        self.value = expires

    def __format__(self, format_spec):
        return self.__str__()

    def __str__(self):
        at_end_of_day = self.value.hour == 23 and self.value.minute == 59 and self.value.second >= 59
        if at_end_of_day:
            return date_format(self.value, "SHORT_DATE_FORMAT")
        else:
            return date_format(self.value, "SHORT_DATETIME_FORMAT")


class LazyCurrencyNumber:
    def __init__(self, value, currency):
        self.value = value
        self.currency = currency

    def __format__(self, format_spec):
        return self.__str__()

    def __str__(self):
        return money_filter(self.value, self.currency)


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
    def __init__(self, *args):
        self.msg = args[0]
        self.msgargs = args[1] if len(args) > 1 else None
        self.args = args
        super().__init__(self.msg, self.msgargs)

    def __str__(self):
        if self.msgargs:
            return gettext(self.msg) % self.msgargs
        else:
            return gettext(self.msg)
