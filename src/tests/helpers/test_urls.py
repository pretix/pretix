from django.conf import settings
from django.core import urlresolvers

from pretix.helpers.urls import build_absolute_uri


def test_site_url_domain():
    settings.SITE_URL = 'https://example.com'
    assert build_absolute_uri('control:auth.login') == 'https://example.com/control/login'


def test_site_url_subpath():
    settings.SITE_URL = 'https://example.com/presale'
    old_prefix = urlresolvers.get_script_prefix()
    urlresolvers.set_script_prefix('/presale/')
    assert build_absolute_uri('control:auth.login') == 'https://example.com/presale/control/login'
    urlresolvers.set_script_prefix(old_prefix)
