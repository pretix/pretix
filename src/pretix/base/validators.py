from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _


class BlacklistValidator:

    blacklist = []

    def __call__(self, value):
        # Validation logic
        if value in self.blacklist:
            message = _("This slug has an invalid value.")
            raise ValidationError(message)


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
