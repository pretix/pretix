from typing import Protocol, runtime_checkable

from django.utils import translation
from django.utils.formats import date_format

type MaybeTranslatedString = str | Localizable


@runtime_checkable
class Localizable(Protocol):
    def localize(self, lng: str) -> str:
        ...


class LocalizableBase:
    def localize(self, lng):
        with translation.override(lng):
            return str(self)


class FormattingLocalizableString(LocalizableBase):
    def __init__(
        self,
        base_str: MaybeTranslatedString,
        *format_args: MaybeTranslatedString,
        **format_kwargs: MaybeTranslatedString,
    ):
        self.base_str = base_str
        self.format_args = format_args
        self.format_kwargs = format_kwargs

    def __str__(self):
        return str(self.base_str).format(*self.format_args, **self.format_kwargs)


class GettextLocalizableString(LocalizableBase):
    def __init__(self, base):
        self.base = base

    @classmethod
    def gettext(cls, base):
        """Fake function so makemessages picks up these strings."""
        return cls(base)

    def __str__(self):
        return translation.gettext(self.base)


class LocalizableDatetime(LocalizableBase):
    def __init__(self, datetime, format):
        self.datetime = datetime
        self.format = format

    def __str__(self):
        return date_format(self.datetime, self.format)


def localizable_to_dict(string: MaybeTranslatedString, locales: list[str]):
    translated = {}

    for locale in locales:
        with translation.override(locale):
            translated[locale] = str(string)

    return translated
