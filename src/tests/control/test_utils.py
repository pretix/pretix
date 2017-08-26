from pretix.base.i18n import language
from pretix.control.utils.i18n import get_javascript_format, get_moment_locale


def test_js_formats():
    with language('de'):
        assert get_javascript_format('DATETIME_INPUT_FORMATS') == 'DD.MM.YYYY HH:mm:ss'
    with language('en'):
        assert get_javascript_format('DATETIME_INPUT_FORMATS') == 'YYYY-MM-DD HH:mm:ss'


def test_get_locale():
    get_moment_locale('af') == 'af'
    get_moment_locale('de_Informal') == 'de'
    get_moment_locale('de-AT') == 'de'
