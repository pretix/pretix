from urllib.parse import urljoin, urlsplit

from django.conf import settings
from django.core.urlresolvers import reverse


def get_domain(event):
    c = event.organizer.get_cache()
    domain = c.get('domain')
    if domain is None:
        domains = event.organizer.domains.all()
        domain = domains[0].domainname if domains else None
        c.set('domain', domain or 'none')
    elif domain == 'none':
        return None
    return domain


def eventreverse(event, name, kwargs=None):
    """
    Works similar to django.core.urlresolvers.reverse but takes into account that some
    organizers might have their own (sub)domain instead of a subpath.
    """
    kwargs = kwargs or {}
    kwargs['event'] = event.slug
    domain = get_domain(event)
    if domain:
        if 'organizer' in kwargs:
            del kwargs['organizer']
        path = reverse(name, kwargs=kwargs)
        siteurlsplit = urlsplit(settings.SITE_URL)
        if siteurlsplit.port and siteurlsplit.port not in (80, 443):
            domain = '%s:%d' % (domain, siteurlsplit.port)
        return urljoin('%s://%s' % (siteurlsplit.scheme, domain), path)

    kwargs['organizer'] = event.organizer.slug
    return reverse(name, kwargs=kwargs)


def build_absolute_uri(event, urlname, kwargs=None):
    reversedurl = eventreverse(event, urlname, kwargs)
    if '://' in reversedurl:
        return reversedurl
    return urljoin(settings.SITE_URL, reversedurl)
