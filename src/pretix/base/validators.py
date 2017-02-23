from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible
from django.utils.translation import ugettext_lazy as _


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
        '__debug__'
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
        'about'
    ]
