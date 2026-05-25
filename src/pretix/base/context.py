#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
import sys

from django.conf import settings
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext

from pretix.base.settings import GlobalSettingsObject
from pretix.base.templatetags.safelink import safelink as sl


def _get_powered_by_data(request=None, safelink=True):
    """
    Look up the configured attribution settings used by `get_powered_by()`
    and `get_email_powered_by()`. Centralising this avoids drift between the
    website and email renderings.
    """
    gs = GlobalSettingsObject()
    d = gs.settings.license_check_input

    pretix_url = sl('https://pretix.eu') if safelink else 'https://pretix.eu'
    name = d.get('poweredby_name')

    name_url = None
    if name and d.get('poweredby_url'):
        name_url = sl(d['poweredby_url']) if safelink else d['poweredby_url']

    source_url = None
    if d.get('base_license') == 'agpl' and request is not None:
        source_url = request.build_absolute_uri(reverse('source'))

    return name, name_url, pretix_url, source_url


def _anchor_attrs(url):
    return 'href="{}" target="_blank" rel="noopener"'.format(url)


def _anchor(url, text):
    return '<a {}>{}</a>'.format(_anchor_attrs(url), text)


def get_powered_by(request, safelink=True):
    name, name_url, pretix_url, source_url = _get_powered_by_data(request, safelink)
    if name:
        if name_url:
            msg = gettext('<a {a_name_attr}>powered by {name}</a> <a {a_attr}>based on pretix</a>').format(
                name=name,
                a_name_attr=_anchor_attrs(name_url),
                a_attr=_anchor_attrs(pretix_url),
            )
        else:
            msg = gettext('<a {a_attr}>powered by {name} based on pretix</a>').format(
                name=name,
                a_attr=_anchor_attrs(pretix_url),
            )

    else:
        msg = gettext('<a %(a_attr)s>ticketing powered by pretix</a>') % {
            'a_attr': _anchor_attrs(pretix_url),
        }

    if source_url:
        msg += ' ({})'.format(_anchor(source_url, gettext('source code')))

    return mark_safe(msg)


def get_email_powered_by():
    """
    Like `get_powered_by()` but renders narrower links: only the configured
    name and the word "pretix" are anchors, the surrounding text stays plain.
    A full-width hyperlinked footer looks visually heavy in HTML emails, and
    the license attribution requirement applies to generated web pages only,
    so this variant is unconstrained.
    """
    name, name_url, pretix_url, _ = _get_powered_by_data(safelink=False)
    pretix_link = _anchor(pretix_url, 'pretix')

    if name:
        name_part = _anchor(name_url, name) if name_url else name
        msg = gettext('powered by {name} based on {pretix}').format(
            name=name_part, pretix=pretix_link,
        )
    else:
        msg = gettext('ticketing powered by {pretix}').format(pretix=pretix_link)

    return mark_safe(msg)


def contextprocessor(request):
    ctx = {
        'rtl': getattr(request, 'LANGUAGE_CODE', 'en') in settings.LANGUAGES_RTL,
    }
    try:
        ctx['poweredby'] = get_powered_by(request, safelink=True)
    except Exception:
        ctx['poweredby'] = '<a href="https://pretix.eu/" target="_blank" rel="noopener">powered by pretix</a>'
    if settings.DEBUG and 'runserver' not in sys.argv:
        ctx['debug_warning'] = True
    elif 'runserver' in sys.argv:
        ctx['development_warning'] = True

    return ctx
