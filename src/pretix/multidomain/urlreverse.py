from urllib.parse import urljoin, urlsplit

from django.conf import settings
from django.core.urlresolvers import reverse

from pretix.base.models import Event, Organizer


def get_domain(organizer):
    c = organizer.get_cache()
    domain = c.get('domain')
    if domain is None:
        domains = organizer.domains.all()
        domain = domains[0].domainname if domains else None
        c.set('domain', domain or 'none')
    elif domain == 'none':
        return None
    return domain


def eventreverse(obj, name, kwargs=None):
    """
    Works similar to django.core.urlresolvers.reverse but takes into account that some
    organizers might have their own (sub)domain instead of a subpath.

    :param obj: An event or organizer
    """
    from pretix.multidomain import subdomain_urlconf, maindomain_urlconf

    kwargs = kwargs or {}
    if isinstance(obj, Event):
        kwargs['event'] = obj.slug
        organizer = obj.organizer
    elif isinstance(obj, Organizer):
        organizer = obj
    else:
        raise TypeError('obj should be Event or Organizer')
    domain = get_domain(organizer)
    if domain:
        if 'organizer' in kwargs:
            del kwargs['organizer']

        path = reverse(name, kwargs=kwargs, urlconf=subdomain_urlconf)
        siteurlsplit = urlsplit(settings.SITE_URL)
        if siteurlsplit.port and siteurlsplit.port not in (80, 443):
            domain = '%s:%d' % (domain, siteurlsplit.port)
        return urljoin('%s://%s' % (siteurlsplit.scheme, domain), path)

    kwargs['organizer'] = organizer.slug
    return reverse(name, kwargs=kwargs, urlconf=maindomain_urlconf)


def build_absolute_uri(obj, urlname, kwargs=None):
    reversedurl = eventreverse(obj, urlname, kwargs)
    if '://' in reversedurl:
        return reversedurl
    return urljoin(settings.SITE_URL, reversedurl)
