from django.conf import settings
from pretix.helpers.urls import build_absolute_uri
from django.core import urlresolvers


def test_site_url_domain():
    settings.SITE_URL = 'https://example.com'
    assert build_absolute_uri('control:auth.login') == 'https://example.com/control/login'


def test_site_url_subpath():
    settings.SITE_URL = 'https://example.com/presale'
    urlresolvers.set_script_prefix('/presale/')
    assert build_absolute_uri('control:auth.login') == 'https://example.com/presale/control/login'
