from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible
from django.utils.translation import ugettext_lazy as _


class BlacklistValidator:

    banlist = []

    def __call__(self, value):
        # Validation logic
        if value in self.banlist:
            raise ValidationError(
                _('This field has an invalid value: %(value)s.'),
                code='invalid',
                params={'value': value},
            )


@deconstructible
class EventSlugBlacklistValidator(BlacklistValidator):

    banlist = [
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
        'widget',
    ]


@deconstructible
class OrganizerSlugBlacklistValidator(BlacklistValidator):

    banlist = [
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
        'widget',
    ]


@deconstructible
class EmailBlacklistValidator(BlacklistValidator):

    banlist = [
        settings.PRETIX_EMAIL_NONE_VALUE,
    ]
