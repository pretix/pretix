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
import json

from django.db.models import prefetch_related_objects
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError


class AsymmetricField(serializers.Field):
    def __init__(self, read, write, **kwargs):
        self.read = read
        self.write = write
        super().__init__(
            required=self.write.required,
            default=self.write.default,
            initial=self.write.initial,
            source=self.write.source if self.write.source != self.write.field_name else None,
            label=self.write.label,
            allow_null=self.write.allow_null,
            error_messages=self.write.error_messages,
            validators=self.write.validators,
            **kwargs
        )

    def to_internal_value(self, data):
        return self.write.to_internal_value(data)

    def to_representation(self, value):
        return self.read.to_representation(value)

    def run_validation(self, data=serializers.empty):
        return self.write.run_validation(data)


class CompatibleJSONField(serializers.JSONField):
    def to_internal_value(self, data):
        try:
            return json.dumps(data)
        except (TypeError, ValueError):
            self.fail('invalid')

    def to_representation(self, value):
        if value:
            return json.loads(value)
        return value


class SalesChannelMigrationMixin:
    """
    Translates between the old field "sales_channels" and the new field combo "all_sales_channels"/"limit_sales_channels".
    """

    @property
    def organizer(self):
        if "organizer" in self.context:
            return self.context["organizer"]
        elif "event" in self.context:
            return self.context["event"].organizer
        else:
            raise ValueError("organizer not in context")

    def to_internal_value(self, data):
        if "sales_channels" in data:
            if data["sales_channels"] is None:
                raise ValidationError({
                    "sales_channels": [
                        "The legacy attribute 'sales_channels' cannot be set to None, it must be a list."
                    ]
                })

            prefetch_related_objects([self.organizer], "sales_channels")
            all_channels = {
                s.identifier for s in
                self.organizer.sales_channels.all()
            }

            if data.get("all_sales_channels") and set(data["sales_channels"]) != all_channels:
                raise ValidationError({
                    "all_sales_channels": [
                        "If 'all_sales_channels' is set, the legacy attribute 'sales_channels' must not be set or set to "
                        "the list of all sales channels."
                    ]
                })

            if data.get("limit_sales_channels") and set(data["sales_channels"]) != set(data["limit_sales_channels"]):
                raise ValidationError({
                    "limit_sales_channels": [
                        "If 'limit_sales_channels' is set, the legacy attribute 'sales_channels' must not be set or set to "
                        "the same list."
                    ]
                })

            if set(data["sales_channels"]) == all_channels:
                data["all_sales_channels"] = True
                data["limit_sales_channels"] = []
            else:
                data["all_sales_channels"] = False
                data["limit_sales_channels"] = data["sales_channels"]

            del data["sales_channels"]

        if data.get("all_sales_channels"):
            data["limit_sales_channels"] = []

        return super().to_internal_value(data)

    def to_representation(self, value):
        value = super().to_representation(value)
        if value.get("all_sales_channels"):
            prefetch_related_objects([self.organizer], "sales_channels")
            value["sales_channels"] = sorted([
                s.identifier for s in
                self.organizer.sales_channels.all()
            ])
        elif "limit_sales_channels" in value:
            value["sales_channels"] = value["limit_sales_channels"]
        return value


class ConfigurableSerializerMixin:
    expand_fields = {}

    def get_exclude_requests(self):
        if hasattr(self, "initial_data"):
            # Do not support include requests when the serializer is used for writing
            # TODO: think about this
            return set()
        if getattr(self, "parent", None):
            # Field selection is always handled by top-level serializer
            return set()
        if 'exclude' in self.context:
            return self.context['exclude']
        elif 'request' in self.context:
            return self.context['request'].query_params.getlist('exclude')
        raise TypeError("Could not discover list of fields to exclude")

    def get_include_requests(self):
        if hasattr(self, "initial_data"):
            # Do not support include requests when the serializer is used for writing
            # TODO: think about this
            return set()
        if getattr(self, "parent", None):
            # Field selection is always handled by top-level serializer
            return set()
        if 'include' in self.context:
            return self.context['include']
        elif 'request' in self.context:
            return self.context['request'].query_params.getlist('include')
        raise TypeError("Could not discover list of fields to include")

    def get_expand_requests(self):
        if hasattr(self, "initial_data"):
            # Do not support expand requests when the serializer is used for writing
            # TODO: think about this
            return set()
        if getattr(self, "parent", None):
            # Field selection is always handled by top-level serializer
            return set()
        if 'expand' in self.context:
            return self.context['expand']
        elif 'request' in self.context:
            return self.context['request'].query_params.getlist('expand')
        raise TypeError("Could not discover list of fields to expand")

    def _exclude_field(self, serializer, path):
        if path[0] not in serializer.fields:
            return  # field does not exist, nothing to do

        if len(path) == 1:
            del serializer.fields[path[0]]
        elif len(path) >= 2 and hasattr(serializer.fields[path[0]], "child"):
            self._exclude_field(serializer.fields[path[0]].child, path[1:])
        elif len(path) >= 2 and isinstance(serializer.fields[path[0]], serializers.Serializer):
            self._exclude_field(serializer.fields[path[0]], path[1:])

    def _filter_fields_to_included(self, serializer, includes):
        any_field_remaining = False
        for fname, field in list(serializer.fields.items()):
            if fname in includes:
                any_field_remaining = True
                continue
            elif hasattr(field, 'child'):  # Nested list serializers
                child_includes = {i.removeprefix(f'{fname}.') for i in includes if i.startswith(f'{fname}.')}
                if child_includes and self._filter_fields_to_included(field.child, child_includes):
                    any_field_remaining = True
                    continue
                serializer.fields.pop(fname)
            elif isinstance(field, serializers.Serializer):  # Nested serializers
                child_includes = {i.removeprefix(f'{fname}.') for i in includes if i.startswith(f'{fname}.')}
                if child_includes and self._filter_fields_to_included(field, child_includes):
                    any_field_remaining = True
                    continue
                serializer.fields.pop(fname)
            else:
                serializer.fields.pop(fname)
        return any_field_remaining

    def _expand_field(self, serializer, path, original_field):
        if path[0] not in serializer.fields or not self.is_field_expandable(original_field):
            return False  # field does not exist, nothing to do

        if len(path) == 1:
            serializer.fields[path[0]] = self.get_expand_serializer(original_field)
            return True
        elif len(path) >= 2 and hasattr(serializer.fields[path[0]], "child"):
            return self._expand_field(serializer.fields[path[0]].child, path[1:], original_field)
        elif len(path) >= 2 and isinstance(serializer.fields[path[0]], serializers.Serializer):
            return self._expand_field(serializer.fields[path[0]], path[1:], original_field)

    def is_field_expandable(self, field):
        return field in self.expand_fields

    def get_expand_serializer(self, field):
        from pretix.base.models import Device, TeamAPIToken

        ef = self.expand_fields[field]
        if "permission" in ef:
            request = self.context["request"]
            perm_holder = request.auth if isinstance(request.auth, (Device, TeamAPIToken)) else request.user
            if not perm_holder.has_event_permission(request.organizer, request.event, ef["permission"], request=request):
                raise PermissionDenied(f"No permission to expand field {field}")

        if hasattr(self, "instance") and "prefetch" in ef:
            for prefetch in ef["prefetch"]:
                prefetch_related_objects(
                    self.instance if hasattr(self.instance, '__iter__') else [self.instance],
                    prefetch
                )

        return ef["serializer"](
            read_only=True,
            context=self.context,
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        expanded = False
        for expand in sorted(list(self.get_expand_requests())):
            expanded = self._expand_field(self, expand.split('.'), expand) or expanded

        includes = set(self.get_include_requests())
        if includes:
            self._filter_fields_to_included(self, includes)

        for exclude_field in self.get_exclude_requests():
            self._exclude_field(self, exclude_field.split('.'))
