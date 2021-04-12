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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: pajowu
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from collections import OrderedDict

from django.core.exceptions import ValidationError
from rest_framework import serializers


def remove_duplicates_from_list(data):
    return list(OrderedDict.fromkeys(data))


class ListMultipleChoiceField(serializers.MultipleChoiceField):
    def to_internal_value(self, data):
        if isinstance(data, str) or not hasattr(data, '__iter__'):
            self.fail('not_a_list', input_type=type(data).__name__)
        if not self.allow_empty and len(data) == 0:
            self.fail('empty')

        internal_value_data = [
            super(serializers.MultipleChoiceField, self).to_internal_value(item)
            for item in data
        ]

        return remove_duplicates_from_list(internal_value_data)

    def to_representation(self, value):
        representation_data = [
            self.choice_strings_to_values.get(str(item), item) for item in value
        ]

        return remove_duplicates_from_list(representation_data)


class UploadedFileField(serializers.Field):
    default_error_messages = {
        'required': 'No file was submitted.',
        'not_found': 'The submitted file ID was not found.',
        'invalid_type': 'The submitted file has a file type that is not allowed in this field.',
        'size': 'The submitted file is too large to be used in this field.',
    }

    def __init__(self, *args, **kwargs):
        self.allowed_types = kwargs.pop('allowed_types', None)
        self.max_size = kwargs.pop('max_size', None)
        super().__init__(*args, **kwargs)

    def to_internal_value(self, data):
        from pretix.base.models import CachedFile

        request = self.context.get('request', None)
        try:
            cf = CachedFile.objects.get(
                session_key=f'api-upload-{str(type(request.user or request.auth))}-{(request.user or request.auth).pk}',
                file__isnull=False,
                pk=data[len("file:"):],
            )
        except (ValidationError, IndexError):  # invalid uuid
            self.fail('not_found')
        except CachedFile.DoesNotExist:
            self.fail('not_found')

        if self.allowed_types and cf.type not in self.allowed_types:
            self.fail('invalid_type')
        if self.max_size and cf.file.size > self.max_size:
            self.fail('size')

        return cf.file

    def to_representation(self, value):
        if not value:
            return None

        try:
            url = value.url
        except AttributeError:
            return None
        request = self.context['request']
        return request.build_absolute_uri(url)
