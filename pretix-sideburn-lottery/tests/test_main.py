from pretix_sideburn_lottery import __version__
from pretix_sideburn_lottery.apps import PluginApp
from pretix_sideburn_lottery.templatetags.ordinal import ordinal


def test_version():
    assert __version__ == "1.0.0"


def test_plugin_metadata():
    meta = PluginApp.PretixPluginMeta
    assert meta.category == "FEATURE"
    assert meta.compatibility == "pretix>=2.7.0"


def test_ordinal_filter():
    assert ordinal(1) == "1st"
    assert ordinal(2) == "2nd"
    assert ordinal(3) == "3rd"
    assert ordinal(4) == "4th"
    assert ordinal(11) == "11th"
    assert ordinal(12) == "12th"
    assert ordinal(13) == "13th"
    assert ordinal(21) == "21st"
    assert ordinal("bad") == "bad"
