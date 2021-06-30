#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
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


def get_powered_by(request, safelink=True):
    gs = GlobalSettingsObject()
    d = gs.settings.license_check_input
    if d.get('poweredby_name'):
        if d.get('poweredby_url'):
            n = '<a href="{}" target="_blank" rel="noopener">{}</a>'.format(
                sl(d['poweredby_url']) if safelink else d['poweredby_url'],
                d['poweredby_name']
            )
        else:
            n = d['poweredby_name']

        msg = gettext('powered by {name} based on <a {a_attr}>pretix</a>').format(
            name=n,
            a_attr='href="{}" target="_blank" rel="noopener"'.format(
                sl('https://pretix.eu') if safelink else 'https://pretix.eu',
            )
        )
    else:
        msg = gettext('<a %(a_attr)s>ticketing powered by pretix</a>') % {
            'a_attr': 'href="{}" target="_blank" rel="noopener"'.format(
                sl('https://pretix.eu') if safelink else 'https://pretix.eu',
            )
        }

    if d.get('base_license') == 'agpl':
        msg += ' (<a href="{}" target="_blank" rel="noopener">{}</a>)'.format(
            request.build_absolute_uri(reverse('source')),
            gettext('source code')
        )

    return mark_safe(msg)


def contextprocessor(request):
    ctx = {
        'rtl': getattr(request, 'LANGUAGE_CODE', 'en') in settings.LANGUAGES_RTL,
    }
    try:
        ctx['poweredby'] = get_powered_by(request, safelink=True)
    except Exception:
        ctx['poweredby'] = 'powered by <a href="https://pretix.eu/" target="_blank" rel="noopener">pretix</a>'
    if settings.DEBUG and 'runserver' not in sys.argv:
        ctx['debug_warning'] = True
    elif 'runserver' in sys.argv:
        ctx['development_warning'] = True

    return ctx
