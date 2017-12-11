from urllib.parse import urljoin, urlsplit

from django.conf import settings
from django.urls import reverse

from pretix.base.models import Event, Organizer


def get_domain(organizer):
    domain = getattr(organizer, '_cached_domain', None) or organizer.cache.get('domain')
    if domain is None:
        domains = organizer.domains.all()
        domain = domains[0].domainname if domains else None
        organizer.cache.set('domain', domain or 'none')
        organizer._cached_domain = domain or 'none'
    elif domain == 'none':
        organizer._cached_domain = 'none'
        return None
    else:
        organizer._cached_domain = domain
    return domain


def mainreverse(name, kwargs=None):
    """
    Works similar to ``django.core.urlresolvers.reverse`` but uses the maindomain URLconf even
    if on a subpath.

    Non-keyword arguments are not supported as we want do discourage using them for better
    readability.

    :param name: The name of the URL route
    :type name: str
    :param kwargs: A dictionary of additional keyword arguments that should be used. You do not
        need to provide the organizer or event slug here, it will be added automatically as
        needed.
    :returns: An absolute URL (including scheme and host) as a string
    """
    from pretix.multidomain import maindomain_urlconf

    kwargs = kwargs or {}
    return reverse(name, kwargs=kwargs, urlconf=maindomain_urlconf)


def eventreverse(obj, name, kwargs=None):
    """
    Works similar to ``django.core.urlresolvers.reverse`` but takes into account that some
    organizers might have their own (sub)domain instead of a subpath.

    Non-keyword arguments are not supported as we want do discourage using them for better
    readability.

    :param obj: An ``Event`` or ``Organizer`` object
    :param name: The name of the URL route
    :type name: str
    :param kwargs: A dictionary of additional keyword arguments that should be used. You do not
        need to provide the organizer or event slug here, it will be added automatically as
        needed.
    :returns: An absolute URL (including scheme and host) as a string
    """
    from pretix.multidomain import subdomain_urlconf, maindomain_urlconf

    c = None
    if not kwargs:
        c = obj.cache
        url = c.get('urlrev_{}'.format(name))
        if url:
            return url

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
    url = reverse(name, kwargs=kwargs, urlconf=maindomain_urlconf)
    if not kwargs and c:
        c.set('urlrev_{}'.format(url), url)
    return url


def build_absolute_uri(obj, urlname, kwargs=None):
    reversedurl = eventreverse(obj, urlname, kwargs)
    if '://' in reversedurl:
        return reversedurl
    return urljoin(settings.SITE_URL, reversedurl)
