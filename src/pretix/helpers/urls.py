from urllib.parse import urljoin

from django.conf import settings
from django.urls import reverse


def build_absolute_uri(urlname, args=None, kwargs=None):
    return urljoin(settings.SITE_URL, reverse(urlname, args=args, kwargs=kwargs))
