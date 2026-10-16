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
import pathlib
import re
from urllib.parse import urljoin
from urllib.request import urlopen

import importlib_metadata as metadata
from django import template
from django.conf import settings
from django.utils.safestring import mark_safe

from pretix.base.middleware import (
    add_to_response_csp_via_request, calculate_csp_hash,
)

register = template.Library()
LOGGER = logging.getLogger(__name__)
_MANIFEST = {}
_MANIFEST_ENTRIES = {}
# TODO more os.path.join ?
MANIFEST_PATH = settings.STATIC_ROOT + "/vite/control/.vite/manifest.json"
MANIFEST_BASE = "vite/control/"

# entry_name -> {"manifest": {...}, "key": "...", "url_base": "..."}
_PLUGIN_REGISTRY = {}


def _discover_plugin_manifests():
    """Discover plugin vite manifests at startup.

    Scans installed pretix plugins for a .vite/manifest.json inside a static
    directory. Only non-editable (wheel) plugins are expected to ship pre-built
    assets; editable plugins are served through the Vite dev server.
    """
    for ep in metadata.entry_points(group='pretix.plugin'):
        dist = ep.dist
        if not dist or not dist.files:
            continue

        try:
            url_info = json.loads(dist.read_text('direct_url.json') or '{}')
            if url_info.get('dir_info', {}).get('editable', False):
                continue  # editable plugins are served via vite dev server
        except Exception:
            pass

        # Find .vite/manifest.json inside a /static/ directory
        try:
            manifest_rel = None
            for f in dist.files:
                if f.name == 'manifest.json' and '/static/' in str(f) and '/.vite/' in str(f):
                    manifest_rel = f
                    break

            if not manifest_rel:
                continue

            manifest_path = pathlib.Path(str(dist.locate_file(manifest_rel)))
            if not manifest_path.exists():
                continue

            plugin_manifest = json.loads(manifest_path.read_text())

            url_base = re.search(r'/static/(.+?)/\.vite/', str(manifest_rel)).group(1) + '/'

            for key, entry in plugin_manifest.items():
                if entry.get('isEntry') and 'name' in entry:
                    _PLUGIN_REGISTRY[entry['name']] = {
                        'manifest': plugin_manifest,
                        'key': key,
                        'url_base': url_base,
                    }
        except Exception:
            LOGGER.warning(f"Failed to discover vite manifest for plugin {ep.name}", exc_info=True)


# Load core manifest
if not settings.VITE_DEV_MODE and not settings.VITE_IGNORE:
    try:
        with open(MANIFEST_PATH) as fp:
            _MANIFEST = json.load(fp)
        _MANIFEST_ENTRIES = {
            entry["name"]: key for key, entry in _MANIFEST.items() if entry.get("isEntry") and "name" in entry
        }
    except Exception as e:
        LOGGER.warning(f"Error reading vite manifest at {MANIFEST_PATH}: {str(e)}")

# Discover plugin manifests
if not settings.VITE_IGNORE:
    _discover_plugin_manifests()


def _generate_script_tag(path, attrs, src=None):
    all_attrs = " ".join(f'{key}="{value}"' for key, value in attrs.items())
    if src is None:
        if settings.VITE_DEV_MODE:
            src = urljoin(settings.VITE_DEV_SERVER, path)
        else:
            src = urljoin(settings.STATIC_URL, path)
    return f'<script {all_attrs} src="{src}"></script>'


def _generate_css_tags(manifest, key, url_base, seen_chunks=None, seen_css=None):
    """
    Builds the CSS tags for a manifest chunk and everything it imports statically.

    Vite lists a chunk's own CSS only. Traverse dependency graph to find all CSS that is imported by this chunk and its dependencies.
    """
    if seen_chunks is None:
        seen_chunks = set()
    if seen_css is None:
        seen_css = set()
    if key in seen_chunks:
        return []
    seen_chunks.add(key)

    manifest_entry = manifest[key]
    tags = []
    for css_path in manifest_entry.get("css", []):
        # Different chunks can reference the same emitted stylesheet.
        if css_path not in seen_css:
            tags.append(f'<link rel="stylesheet" href="{urljoin(settings.STATIC_URL, url_base + css_path)}" />')
            seen_css.add(css_path)
    for import_key in manifest_entry.get("imports", []):
        tags += _generate_css_tags(manifest, import_key, url_base, seen_chunks, seen_css)
    return tags


@register.simple_tag
@mark_safe
def vite_asset(path):
    """
    Generates one <script> tag and <link> tags for each of the CSS dependencies.
    """

    if not path:
        return ""

    # Check plugin registry (non-editable plugins with pre-built assets)
    if path in _PLUGIN_REGISTRY:
        info = _PLUGIN_REGISTRY[path]
        manifest, key, url_base = info['manifest'], info['key'], info['url_base']
        tags = _generate_css_tags(manifest, key, url_base)
        # Always use STATIC_URL for pre-built plugin assets, even in dev mode
        src = urljoin(settings.STATIC_URL, url_base + manifest[key]["file"])
        tags.append(_generate_script_tag(path, {"type": "module", "crossorigin": ""}, src=src))
        return "".join(tags)

    # Dev mode: editable plugins and core entries go through the vite dev server
    if settings.VITE_DEV_MODE:
        return _generate_script_tag(path, {"type": "module"})

    # Prod mode: core addresses entries by source path (the manifest key), plugins by entry name
    key = _MANIFEST_ENTRIES.get(path, path)
    manifest_entry = _MANIFEST.get(key)
    if not manifest_entry:
        raise RuntimeError(f"Cannot find {path} in Vite manifest at {MANIFEST_PATH}")

    tags = _generate_css_tags(_MANIFEST, key, MANIFEST_BASE)
    tags.append(
        _generate_script_tag(
            MANIFEST_BASE + manifest_entry["file"], {"type": "module", "crossorigin": ""}
        )
    )
    return "".join(tags)


@register.simple_tag
@mark_safe
def vite_hmr():
    if not settings.VITE_DEV_MODE:
        return ""
    return _generate_script_tag("@vite/client", {"type": "module"})


_dev_importmap_cache = None


def _get_dev_importmap():
    """Fetch the shared-dep import map from the Vite dev server. Cached after first successful fetch."""
    global _dev_importmap_cache
    if _dev_importmap_cache is not None:
        return _dev_importmap_cache
    try:
        url = urljoin(settings.VITE_DEV_SERVER, "/__pretix_importmap")
        raw = json.loads(urlopen(url, timeout=2).read())
        _dev_importmap_cache = {
            dep: urljoin(settings.VITE_DEV_SERVER, dep_path)
            for dep, dep_path in raw.items()
        }
    except Exception:
        LOGGER.warning("Failed to fetch import map from Vite dev server")
        return {}
    return _dev_importmap_cache


@register.simple_tag(takes_context=True)
@mark_safe
def vite_importmap(context):
    """Emit an import map so pre-built plugin assets can resolve shared dependencies like vue."""
    imports = {}

    if settings.VITE_DEV_MODE:
        # Fetch the import map from the Vite dev server (served by sharedDepsPlugin)
        imports.update(_get_dev_importmap())
    else:
        # Discover all _vendor/* entries from the core manifest
        for _key, entry in _MANIFEST.items():
            name = entry.get("name", "")
            if name.startswith("_vendor/"):
                bare_specifier = name[len("_vendor/"):]
                imports[bare_specifier] = urljoin(settings.STATIC_URL, MANIFEST_BASE + entry["file"])

    if not imports:
        return ""

    json_string = json.dumps({"imports": imports})

    # Calculate hash and add it to the CSP info in the request, so that will be merged into the
    # response header later on by the middleware
    request = context.get('request')
    if request:
        csp_hash = calculate_csp_hash(json_string)
        add_to_response_csp_via_request(request, {
            'style-src': [csp_hash],
            'script-src': [csp_hash],
        })

    return f'<script type="importmap">{json_string}</script>'
