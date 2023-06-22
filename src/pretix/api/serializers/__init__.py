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

from rest_framework import serializers


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
