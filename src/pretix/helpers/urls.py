from urllib.parse import urljoin
from django.conf import settings
from django.core.urlresolvers import reverse


def build_absolute_uri(urlname, args=None, kwargs=None):
    # Pass prefix='' as a possible SCRIPT_PREFIX (if pretix runs in a subdirectory)
    # is included in SITE_URL _and_ is added by reverse.
    return urljoin(settings.SITE_URL, reverse(urlname, args=args, kwargs=kwargs, prefix=''))
