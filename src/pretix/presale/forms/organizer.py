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
from django import forms
from django.conf import settings
from django.utils.translation import pgettext
from i18nfield.strings import LazyI18nString

from pretix.base.models import EventMetaValue, SubEventMetaValue


def meta_filtersets(organizer, event=None):
    fields = {}
    if not (event or organizer).settings.event_list_filters:
        return fields
    for prop in organizer.meta_properties.filter(filter_public=True):
        if prop.choices:
            choices = [(v["key"], str(LazyI18nString(v["label"])) or v["key"]) for v in prop.choices]
        elif event:
            existing_values = set()
            if event.meta_data.get(prop.name):
                existing_values.add(event.meta_data.get(prop.name))
            existing_values |= set(SubEventMetaValue.objects.using(settings.DATABASE_REPLICA).filter(
                property=prop,
                subevent__event=event,
                subevent__event__live=True,
                subevent__event__is_public=True,
                subevent__active=True,
                subevent__is_public=True,
            ).values_list("value", flat=True).distinct())
            choices = [(k, k) for k in sorted(existing_values)]
        else:
            existing_values = set()
            if prop.default:
                existing_values.add(prop.default)
            existing_values |= set(EventMetaValue.objects.using(settings.DATABASE_REPLICA).filter(
                property=prop,
                event__organizer=organizer,
                event__live=True,
                event__is_public=True,
            ).values_list("value", flat=True).distinct())
            existing_values |= set(SubEventMetaValue.objects.using(settings.DATABASE_REPLICA).filter(
                property=prop,
                subevent__event__organizer=organizer,
                subevent__event__live=True,
                subevent__event__is_public=True,
                subevent__active=True,
                subevent__is_public=True,
            ).values_list("value", flat=True).distinct())
            choices = [(k, k) for k in sorted(existing_values)]

        choices.insert(0, ("", "-- %s --" % pgettext("filter_empty", "all")))
        if len(choices) > 1:
            fields[f"attr[{prop.name}]"] = {
                "label": str(prop.public_label) or prop.name,
                "choices": choices
            }
    return fields


class EventListFilterForm(forms.Form):

    def __init__(self, *args, **kwargs):
        self.organizer = kwargs.pop('organizer')
        self.event = kwargs.pop('event', None)
        super().__init__(*args, **kwargs)

        for k, v in meta_filtersets(self.organizer, self.event).items():
            self.fields[k] = forms.ChoiceField(
                label=v["label"],
                choices=v["choices"],
                required=False,
            )
