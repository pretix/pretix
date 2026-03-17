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

import json
import logging
from urllib.parse import urljoin

from django import template
from django.conf import settings
from django.utils.safestring import mark_safe

register = template.Library()
LOGGER = logging.getLogger(__name__)
_MANIFEST = {}
# TODO more os.path.join ?
MANIFEST_PATH = settings.STATIC_ROOT + "/vite/control/.vite/manifest.json"
MANIFEST_BASE = "vite/control/"

# We're building the manifest if we don't have a dev server running AND if we're
# not currently running `rebuild` (which creates the manifest in the first place).
if not settings.VITE_DEV_MODE and not settings.VITE_IGNORE:
    try:
        with open(MANIFEST_PATH) as fp:
            _MANIFEST = json.load(fp)
    except Exception as e:
        LOGGER.warning(f"Error reading vite manifest at {MANIFEST_PATH}: {str(e)}")


def generate_script_tag(path, attrs):
    all_attrs = " ".join(f'{key}="{value}"' for key, value in attrs.items())
    if settings.VITE_DEV_MODE:
        src = urljoin(settings.VITE_DEV_SERVER, path)
    else:
        src = urljoin(settings.STATIC_URL, path)
    return f'<script {all_attrs} src="{src}"></script>'


def generate_css_tags(asset, already_processed=None):
    """Recursively builds all CSS tags used in a given asset.

    Ignore the side effects."""
    tags = []
    manifest_entry = _MANIFEST[asset]
    if already_processed is None:
        already_processed = []

    # Put our own CSS file first for specificity
    if "css" in manifest_entry:
        for css_path in manifest_entry["css"]:
            if css_path not in already_processed:
                full_path = urljoin(settings.STATIC_URL, MANIFEST_BASE + css_path)
                tags.append(f'<link rel="stylesheet" href="{full_path}" />')
            already_processed.append(css_path)

    # Import each file only one by way of side effects in already_processed
    if "imports" in manifest_entry:
        for import_path in manifest_entry["imports"]:
            tags += generate_css_tags(import_path, already_processed)

    return tags


@register.simple_tag
@mark_safe
def vite_asset(path):
    """
    Generates one <script> tag and <link> tags for each of the CSS dependencies.
    """

    if not path:
        return ""

    if settings.VITE_DEV_MODE:
        return generate_script_tag(path, {"type": "module"})

    manifest_entry = _MANIFEST.get(path)
    if not manifest_entry:
        raise RuntimeError(f"Cannot find {path} in Vite manifest at {MANIFEST_PATH}")

    tags = generate_css_tags(path)
    tags.append(
        generate_script_tag(
            MANIFEST_BASE + manifest_entry["file"], {"type": "module", "crossorigin": ""}
        )
    )
    return "".join(tags)


@register.simple_tag
@mark_safe
def vite_hmr():
    if not settings.VITE_DEV_MODE:
        return ""
    return generate_script_tag("@vite/client", {"type": "module"})
