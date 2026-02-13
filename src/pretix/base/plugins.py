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
import os
import sys
from enum import Enum
from typing import List

import importlib_metadata as metadata
from django.apps import AppConfig, apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy as _
from django_scopes import scope
from packaging.requirements import Requirement

PLUGIN_LEVEL_EVENT = 'event'
PLUGIN_LEVEL_ORGANIZER = 'organizer'
PLUGIN_LEVEL_EVENT_ORGANIZER_HYBRID = 'event_organizer'


class PluginType(Enum):
    """
    Plugin type classification. THIS IS DEPRECATED, DO NOT USE ANY MORE.
    This is only not removed yet as external plugins might have references
    to this enum.
    """
    RESTRICTION = 1
    PAYMENT = 2
    ADMINFEATURE = 3
    EXPORT = 4


def get_all_plugins(*, event=None, organizer=None) -> List[type]:
    """
    Returns the PretixPluginMeta classes of all plugins found in the installed Django apps.
    """
    assert not event or not organizer
    plugins = []
    event_fallback = None
    event_fallback_used = False
    for app in apps.get_app_configs():
        if hasattr(app, 'PretixPluginMeta'):
            meta = app.PretixPluginMeta
            meta.module = app.name
            meta.app = app
            if app.name in settings.PRETIX_PLUGINS_EXCLUDE:
                continue

            level = getattr(meta, "level", PLUGIN_LEVEL_EVENT)
            if level == PLUGIN_LEVEL_EVENT:
                if event and hasattr(app, 'is_available'):
                    if not app.is_available(event):
                        continue
                elif organizer and hasattr(app, 'is_available'):
                    if not event_fallback_used:
                        with scope(organizer=organizer):
                            event_fallback = organizer.events.first()
                        event_fallback_used = True
                    if not event_fallback or not app.is_available(event_fallback):
                        continue
            elif level == PLUGIN_LEVEL_ORGANIZER:
                if organizer and hasattr(app, 'is_available'):
                    if not app.is_available(organizer):
                        continue
                elif event and hasattr(app, 'is_available'):
                    if not app.is_available(event.organizer):
                        continue
            elif level == PLUGIN_LEVEL_EVENT_ORGANIZER_HYBRID and (event or organizer) and hasattr(app, 'is_available'):
                if not app.is_available(event or organizer):
                    continue

            plugins.append(meta)
    return sorted(
        plugins,
        key=lambda m: (0 if m.module.startswith('pretix.') else 1, str(m.name).lower().replace('pretix ', ''))
    )


class PluginConfigMeta(type):
    def __getattribute__(cls, item):
        if item == "default" and cls is PluginConfig:
            return False
        return super().__getattribute__(item)


class PluginConfig(AppConfig, metaclass=PluginConfigMeta):
    IGNORE = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not hasattr(self, 'PretixPluginMeta'):
            raise ImproperlyConfigured("A pretix plugin config should have a PretixPluginMeta inner class.")

        if hasattr(self.PretixPluginMeta, 'compatibility') and not os.environ.get("PRETIX_IGNORE_CONFLICTS") == "True":
            req = Requirement(self.PretixPluginMeta.compatibility)
            requirement_version = metadata.version(req.name)
            if not req.specifier.contains(requirement_version, prereleases=True):
                print("Incompatible plugins found!")
                print("Plugin {} requires you to have {}, but you installed {}.".format(
                    self.name, req, requirement_version
                ))
                sys.exit(1)

        if not hasattr(self.PretixPluginMeta, 'level'):
            self.PretixPluginMeta.level = PLUGIN_LEVEL_EVENT
        if self.PretixPluginMeta.level not in (PLUGIN_LEVEL_EVENT, PLUGIN_LEVEL_ORGANIZER, PLUGIN_LEVEL_EVENT_ORGANIZER_HYBRID):
            raise ImproperlyConfigured(f"Unknown plugin level '{self.PretixPluginMeta.level}'")


CATEGORY_ORDER = [
    'FEATURE',
    'PAYMENT',
    'INTEGRATION',
    'CUSTOMIZATION',
    'FORMAT',
    'API',
]
CATEGORY_LABELS = {
    'FEATURE': _('Features'),
    'PAYMENT': _('Payment providers'),
    'INTEGRATION': _('Integrations'),
    'CUSTOMIZATION': _('Customizations'),
    'FORMAT': _('Output and export formats'),
    'API': _('API features'),
}
