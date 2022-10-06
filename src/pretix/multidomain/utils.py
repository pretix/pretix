from urllib.parse import urljoin, urlsplit

from django.conf import settings
from django.templatetags.static import static

from pretix.base.models import Event
from pretix.multidomain.urlreverse import (
    get_event_domain, get_organizer_domain,
)


def static_absolute(object, path):
    sp = static(path)
    if sp.startswith("/"):
        if isinstance(object, Event):
            domain = get_event_domain(object, fallback=True)
        else:
            domain = get_organizer_domain(object)
        if domain:
            siteurlsplit = urlsplit(settings.SITE_URL)
            if siteurlsplit.port and siteurlsplit.port not in (80, 443):
                domain = '%s:%d' % (domain, siteurlsplit.port)
            sp = urljoin('%s://%s' % (siteurlsplit.scheme, domain), sp)
        else:
            sp = urljoin(settings.SITE_URL, sp)
    return sp
