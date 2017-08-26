"""pretix sphinx theme.

Based on sphinx-rtd-theme
Based on https://github.com/ryan-roemer/sphinx-bootstrap-theme.

"""
import os

__version__ = '0.1.0'
__version_full__ = __version__


def get_html_theme_path():
    """Return list of HTML theme paths."""
    cur_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    return cur_dir
