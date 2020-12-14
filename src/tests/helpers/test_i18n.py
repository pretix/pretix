from django.utils.translation import get_language

from pretix.base.i18n import get_language_without_region, language
from pretix.helpers.i18n import get_javascript_format, get_moment_locale


def test_js_formats():
    with language('de'):
        assert get_javascript_format('DATE_INPUT_FORMATS') == 'DD.MM.YYYY'
    with language('en'):
        assert get_javascript_format('DATE_INPUT_FORMATS') == 'YYYY-MM-DD'
    with language('en-US'):
        assert get_javascript_format('DATE_INPUT_FORMATS') == 'MM/DD/YYYY'


def test_get_locale():
    assert get_moment_locale('af') == 'af'
    assert get_moment_locale('de_Informal') == 'de'
    assert get_moment_locale('de-US') == 'de'
    assert get_moment_locale('en-US') == 'en'
    assert get_moment_locale('en-CA') == 'en-ca'


def test_set_region():
    with language('de'):
        assert get_language() == 'de'
        assert get_language_without_region() == 'de'
    with language('de', 'US'):
        assert get_language() == 'de-us'
        assert get_language_without_region() == 'de'
    with language('de', 'DE'):
        assert get_language() == 'de-de'
        assert get_language_without_region() == 'de'
    with language('de-informal', 'DE'):
        assert get_language() == 'de-informal'
        assert get_language_without_region() == 'de-informal'
    with language('pt', 'BR'):
        assert get_language() == 'pt-br'
        assert get_language_without_region() == 'pt-br'
    with language('pt-br', 'PT'):
        assert get_language() == 'pt-br'
        assert get_language_without_region() == 'pt-br'
