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
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _
from reportlab.lib import pagesizes
from reportlab.lib.units import mm


def _simple_template(w, h):
    name_size = max(min(20, w / 20), 12)  # Heuristic for font size
    company_size = name_size - 2
    return [
        {
            "type": "textcontainer",
            "page": 1,
            "locale": "",
            "left": "5.00",
            "bottom": "%.2f" % (h / mm / 2 + 2),
            "fontsize": name_size,
            "lineheight": "1",
            "color": [0, 0, 0, 1],
            "fontfamily": "Open Sans",
            "bold": True,
            "italic": False,
            "width": "%.2f" % (w / mm - 10),
            "height": "%.2f" % (h / mm / 2 - 7),
            "content": "attendee_name",
            "text": "Dr John Doe",
            "text_i18n": {},
            "rotation": 0,
            "align": "center",
            "verticalalign": "bottom",
            "autoresize": True,
            "splitlongwords": False,
        },
        {
            "type": "textcontainer",
            "page": 1,
            "locale": "",
            "left": "5.00",
            "bottom": "5.00",
            "fontsize": company_size,
            "lineheight": "1",
            "color": [0, 0, 0, 1],
            "fontfamily": "Open Sans",
            "bold": False,
            "italic": False,
            "width": "%.2f" % (w / mm - 10),
            "height": "%.2f" % (h / mm / 2 - 7),
            "content": "attendee_company",
            "text": "Sample company",
            "text_i18n": {},
            "rotation": 0,
            "align": "center",
            "verticalalign": "top",
            "autoresize": True,
            "splitlongwords": False,
        },
    ]


TEMPLATES = {
    "a6l": {
        "label": _("A6 landscape"),
        "pagesize": pagesizes.landscape(pagesizes.A6),
        "layout": _simple_template(*pagesizes.landscape(pagesizes.A6)),
    },
    "a6p": {
        "label": _("A6 portrait"),
        "pagesize": pagesizes.portrait(pagesizes.A6),
        "layout": _simple_template(*pagesizes.portrait(pagesizes.A6)),
    },
    "a7l": {
        "label": _("A7 landscape"),
        "pagesize": pagesizes.landscape(pagesizes.A7),
        "layout": _simple_template(*pagesizes.landscape(pagesizes.A7)),
    },
    "a7p": {
        "label": _("A7 portrait"),
        "pagesize": pagesizes.portrait(pagesizes.A7),
        "layout": _simple_template(*pagesizes.portrait(pagesizes.A7)),
    },
    "82x203butterfly": {
        "label": format_lazy(
            _("{width} x {height} mm butterfly badge"), width=82, height=203
        ),
        "pagesize": (82 * mm, 203 * mm),
        "layout": [
            {
                "type": "textcontainer",
                "page": 1,
                "locale": "",
                "left": "5.00",
                "bottom": "153.00",
                "fontsize": "20.0",
                "lineheight": "1",
                "color": [0, 0, 0, 1],
                "fontfamily": "Open Sans",
                "bold": True,
                "italic": False,
                "width": "72.00",
                "height": "20.00",
                "content": "attendee_name",
                "text": "Dr John Doe",
                "text_i18n": {},
                "rotation": 0,
                "align": "center",
                "verticalalign": "bottom",
                "autoresize": True,
                "splitlongwords": False,
            },
            {
                "type": "textcontainer",
                "page": 1,
                "locale": "",
                "left": "5.00",
                "bottom": "132.10",
                "fontsize": "18.0",
                "lineheight": "1",
                "color": [0, 0, 0, 1],
                "fontfamily": "Open Sans",
                "bold": False,
                "italic": False,
                "width": "72.00",
                "height": "20.00",
                "content": "attendee_company",
                "text": "Sample company",
                "text_i18n": {},
                "rotation": 0,
                "align": "center",
                "verticalalign": "top",
                "autoresize": True,
                "splitlongwords": False,
            },
            {
                "type": "textcontainer",
                "page": 1,
                "locale": "",
                "left": "76.97",
                "bottom": "10.86",
                "fontsize": "20.0",
                "lineheight": "1",
                "color": [0, 0, 0, 1],
                "fontfamily": "Open Sans",
                "bold": True,
                "italic": False,
                "width": "72.00",
                "height": "20.00",
                "content": "attendee_name",
                "text": "Dr John Doe",
                "text_i18n": {},
                "rotation": -180,
                "align": "center",
                "verticalalign": "bottom",
                "autoresize": True,
                "splitlongwords": False,
            },
            {
                "type": "textcontainer",
                "page": 1,
                "locale": "",
                "left": "77.07",
                "bottom": "31.76",
                "fontsize": "18.0",
                "lineheight": "1",
                "color": [0, 0, 0, 1],
                "fontfamily": "Open Sans",
                "bold": False,
                "italic": False,
                "width": "72.00",
                "height": "20.00",
                "content": "attendee_company",
                "text": "Sample company",
                "text_i18n": {},
                "rotation": -180,
                "align": "center",
                "verticalalign": "top",
                "autoresize": True,
                "splitlongwords": False,
            },
        ],
    },
    "100x50": {
        "label": format_lazy(_("{width} x {height} mm label"), width=100, height=50),
        "pagesize": (100 * mm, 50 * mm),
        "layout": _simple_template(100 * mm, 50 * mm),
    },
    "83x50": {
        "label": format_lazy(_("{width} x {height} mm label"), width=83, height=50),
        "pagesize": (83 * mm, 50 * mm),
        "layout": _simple_template(83 * mm, 50 * mm),
    },
    "80x50": {
        "label": format_lazy(_("{width} x {height} mm label"), width=80, height=50),
        "pagesize": (80 * mm, 50 * mm),
        "layout": _simple_template(80 * mm, 50 * mm),
    },
    "75x52": {
        "label": format_lazy(_("{width} x {height} mm label"), width=75, height=52),
        "pagesize": (75 * mm, 52 * mm),
        "layout": _simple_template(75 * mm, 52 * mm),
    },
    "70x36": {
        "label": format_lazy(_("{width} x {height} mm label"), width=70, height=36),
        "pagesize": (70 * mm, 36 * mm),
        "layout": _simple_template(70 * mm, 36 * mm),
    },
    "63x29": {
        "label": format_lazy(_("{width} x {height} mm label"), width=63, height=29),
        "pagesize": (63.5 * mm, 29.6 * mm),
        "layout": _simple_template(63.5 * mm, 29.6 * mm),
    },
    "60x90": {
        "label": format_lazy(_("{width} x {height} mm label"), width=60, height=90),
        "pagesize": (60 * mm, 90 * mm),
        "layout": _simple_template(60 * mm, 90 * mm),
    },
    "54x90": {
        "label": format_lazy(_("{width} x {height} mm label"), width=54, height=90),
        "pagesize": (54 * mm, 90 * mm),
        "layout": _simple_template(54 * mm, 90 * mm),
    },
    "50x80": {
        "label": format_lazy(_("{width} x {height} mm label"), width=50, height=80),
        "pagesize": (50 * mm, 80 * mm),
        "layout": _simple_template(50 * mm, 80 * mm),
    },
    "40x75": {
        "label": format_lazy(_("{width} x {height} mm label"), width=40, height=75),
        "pagesize": (40 * mm, 75 * mm),
        "layout": _simple_template(40 * mm, 75 * mm),
    },
    "40x40": {
        "label": format_lazy(_("{width} x {height} mm label"), width=40, height=40),
        "pagesize": (40 * mm, 40 * mm),
        "layout": _simple_template(40 * mm, 40 * mm),
    },
    "88.9x33.87": {
        "label": format_lazy(
            _("{width} x {height} mm label"), width=88.9, height=33.87
        ),
        "pagesize": (88.9 * mm, 33.87 * mm),
        "layout": _simple_template(88.9 * mm, 33.87 * mm),
    },
}
