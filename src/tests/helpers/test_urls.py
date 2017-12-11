from django import urls
from django.conf import settings

from pretix.helpers.urls import build_absolute_uri


def test_site_url_domain():
    settings.SITE_URL = 'https://example.com'
    assert build_absolute_uri('control:auth.login') == 'https://example.com/control/login'


def test_site_url_subpath():
    settings.SITE_URL = 'https://example.com/presale'
    old_prefix = urls.get_script_prefix()
    urls.set_script_prefix('/presale/')
    assert build_absolute_uri('control:auth.login') == 'https://example.com/presale/control/login'
    urls.set_script_prefix(old_prefix)
