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
import logging
import os
from urllib.parse import urljoin, urlsplit

import sass
from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static as _static

from pretix.base.models import Event, Organizer
from pretix.base.signals import EventPluginSignal, GlobalSignal
from pretix.multidomain.urlreverse import (
    get_event_domain, get_organizer_domain,
)

logger = logging.getLogger('pretix.presale.style')


register_fonts = GlobalSignal()
"""
Return a dictionaries of the following structure. Paths should be relative to static root or an absolute URL. In the
latter case, the fonts won't be available for PDF-rendering.

{
    "font name": {
        "regular": {
            "truetype": "….ttf",
            "woff": "…",
            "woff2": "…"
        },
        "bold": {
            ...
        },
        "italic": {
            ...
        },
        "bolditalic": {
            ...
        },
        "pdf_only": False,   # if True, font is not usable on the web
    }
}
"""

register_event_fonts = EventPluginSignal()
"""
Return a dictionaries of the following structure. Paths should be relative to static root or an absolute URL. In the
latter case, the fonts won't be available for PDF-rendering.
As with all event plugin signals, the ``sender`` keyword argument will contain the event.

{
    "font name": {
        "regular": {
            "truetype": "….ttf",
            "woff": "…",
            "woff2": "…"
        },
        "bold": {
            ...
        },
        "italic": {
            ...
        },
        "bolditalic": {
            ...
        },
        "pdf_only": False,   # if True, font is not usable on the web,
    }
}
"""


def get_fonts(event: Event = None, pdf_support_required=False):
    def nested_dict_values(d):
        for v in d.values():
            if isinstance(v, dict):
                yield from nested_dict_values(v)
            else:
                if isinstance(v, str):
                    yield v

    f = {}
    received_fonts = {}

    for recv, value in register_fonts.send(0):
        received_fonts.update(value)

    # When deleting an event, the function is still getting called with an event.
    # We check specifically if there is a PK present to make sure the event actually exists.
    if event and event.pk:
        for recv, value in register_event_fonts.send(event):
            received_fonts.update(value)

    for font, payload in received_fonts.items():
        if pdf_support_required:
            if any('//' in v for v in list(nested_dict_values(payload))):
                continue
            f.update({font: payload})
        else:
            if payload.get('pdf_only', False):
                continue
            f.update({font: payload})

    return f


def get_font_stylesheet(font_name, organizer: Organizer = None, event: Event = None, absolute=True):
    def static(path):
        sp = _static(path)
        if sp.startswith("/") and absolute:
            if event:
                domain = get_event_domain(event, fallback=True)
            elif organizer:
                domain = get_organizer_domain(organizer)
            else:
                domain = None
            if domain:
                siteurlsplit = urlsplit(settings.SITE_URL)
                if siteurlsplit.port and siteurlsplit.port not in (80, 443):
                    domain = '%s:%d' % (domain, siteurlsplit.port)
                sp = urljoin('%s://%s' % (siteurlsplit.scheme, domain), sp)
            else:
                sp = urljoin(settings.SITE_URL, sp)
        return sp

    stylesheet = []
    font = get_fonts(event)[font_name]
    for sty, formats in font.items():
        if sty == 'sample':
            continue
        stylesheet.append('@font-face { ')
        stylesheet.append('font-family: "{}";'.format(font_name))
        if sty in ("italic", "bolditalic"):
            stylesheet.append("font-style: italic;")
        else:
            stylesheet.append("font-style: normal;")
        if sty in ("bold", "bolditalic"):
            stylesheet.append("font-weight: bold;")
        else:
            stylesheet.append("font-weight: normal;")

        srcs = []
        for f in ["woff2", "woff", "truetype"]:
            if f in formats:
                if formats[f].startswith('https'):
                    srcs.append(f"url('{formats[f]}') format('{f}')")
                else:
                    srcs.append(f"url('{static(formats[f])}') format('{f}')")
        stylesheet.append("src: {};".format(", ".join(srcs)))
        stylesheet.append("font-display: swap;")
        stylesheet.append("}")
    return "\n".join(stylesheet)


def get_theme_vars_css(obj, widget=False):
    sassrules = []
    if obj.settings.get("primary_color"):
        sassrules.append("$in-brand-primary: {};".format(obj.settings.get("primary_color")))
    if obj.settings.get("theme_color_success"):
        sassrules.append("$in-brand-success: {};".format(obj.settings.get("theme_color_success")))
    if obj.settings.get("theme_color_danger"):
        sassrules.append("$in-brand-danger: {};".format(obj.settings.get("theme_color_danger")))
    if obj.settings.get("theme_color_background"):
        sassrules.append("$in-body-bg: {};".format(obj.settings.get("theme_color_background")))
    if not obj.settings.get("theme_round_borders"):
        sassrules.append("$in-border-radius-base: 0;")
        sassrules.append("$in-border-radius-large: 0;")
        sassrules.append("$in-border-radius-small: 0;")

    font = obj.settings.get("primary_font")
    if font != "Open Sans" and not widget:
        sassrules.append(get_font_stylesheet(
            font,
            event=obj if isinstance(obj, Event) else None,
            organizer=obj.organizer if isinstance(obj, Event) else obj,
            absolute=False,
        ))
        sassrules.append(
            '$in-font-family-sans-serif: "{}", "Open Sans", "OpenSans", "Helvetica Neue", Helvetica, Arial, sans-serif;'.format(
                font
            )
        )

    if widget:
        sassrules.append("$widget: true;")

    with open(finders.find("pretixbase/scss/_theme_variables.scss"), "r") as f:
        source_scss = f.read()
        sassrules.append(source_scss)

    sassdir = os.path.join(settings.STATIC_ROOT, "pretixbase/scss")
    sassrule = "\n".join(sassrules)
    if not sassrule.strip():
        return ""
    css = sass.compile(
        string=sassrule,
        include_paths=[sassdir]
    )
    return css
