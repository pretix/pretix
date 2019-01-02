from urllib.parse import urljoin

from django.conf import settings
from django.urls import reverse


def build_absolute_uri(urlname, args=None, kwargs=None):
    from pretix.multidomain import maindomain_urlconf

    return urljoin(settings.SITE_URL, reverse(urlname, args=args, kwargs=kwargs, urlconf=maindomain_urlconf))
