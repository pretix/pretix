from urllib.parse import urljoin, urlsplit

from django.conf import settings
from django.db.models import Q
from django.urls import reverse

from pretix.base.models import Event, Organizer

from .models import KnownDomain


def get_event_domain(event, fallback=False, return_info=False):
    assert isinstance(event, Event)
    suffix = ('_fallback' if fallback else '') + ('_info' if return_info else '')
    domain = getattr(event, '_cached_domain' + suffix, None) or event.cache.get('domain' + suffix)
    if domain is None:
        domain = None, None
        if fallback:
            domains = KnownDomain.objects.filter(
                Q(event=event) | Q(organizer_id=event.organizer_id, event__isnull=True)
            )
            domains_event = [d for d in domains if d.event_id == event.pk]
            domains_org = [d for d in domains if not d.event_id]
            if domains_event:
                domain = domains_event[0].domainname, "event"
            elif domains_org:
                domain = domains_org[0].domainname, "organizer"
        else:
            domains = event.domains.all()
            domain = domains[0].domainname if domains else None, "event"
        event.cache.set('domain' + suffix, domain or 'none')
        setattr(event, '_cached_domain' + suffix, domain or 'none')
    elif domain == 'none':
        setattr(event, '_cached_domain' + suffix, 'none')
        domain = None, None
    else:
        setattr(event, '_cached_domain' + suffix, domain)
    return domain if return_info or not isinstance(domain, tuple) else domain[0]


def get_organizer_domain(organizer):
    assert isinstance(organizer, Organizer)
    domain = getattr(organizer, '_cached_domain', None) or organizer.cache.get('domain')
    if domain is None:
        domains = organizer.domains.filter(event__isnull=True)
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
    organizers or events might have their own (sub)domain instead of a subpath.

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
    from pretix.multidomain import (
        event_domain_urlconf, maindomain_urlconf, organizer_domain_urlconf,
    )

    c = None
    if not kwargs:
        c = obj.cache
        url = c.get('urlrev_{}'.format(name))
        if url:
            return url

    kwargs = kwargs or {}
    if isinstance(obj, Event):
        organizer = obj.organizer
        event = obj
        kwargs['event'] = obj.slug
    elif isinstance(obj, Organizer):
        organizer = obj
        event = None
    else:
        raise TypeError('obj should be Event or Organizer')

    if event:
        domain, domaintype = get_event_domain(obj, fallback=True, return_info=True)
    else:
        domain, domaintype = get_organizer_domain(organizer), "organizer"

    if domain:
        if domaintype == "event" and 'event' in kwargs:
            del kwargs['event']
        if 'organizer' in kwargs:
            del kwargs['organizer']

        path = reverse(name, kwargs=kwargs, urlconf=event_domain_urlconf if domaintype == "event" else organizer_domain_urlconf)
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
