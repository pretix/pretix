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
from rest_framework.fields import SerializerMethodField

from pretix.api.auth.utils import get_session_key_for_api_request


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
                file__isnull=False,
                pk=data[len("file:"):],
            )
            if cf.session_key == "api-upload-<class 'django.contrib.auth.models.AnonymousUser'>-None":
                # OK, backwards-compatibility of a security bug fixed 2026-09, delete this at some point, but should
                # also be harmless because all files with this key are expired one day after deployment of this fix
                # and no new files with this key are created
                pass
            elif cf.session_key != get_session_key_for_api_request(request):
                self.fail('not_found')
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


class PluginsField(serializers.Field):

    def to_representation(self, obj):
        from pretix.base.plugins import get_all_plugins
        active_plugins = set(obj.get_plugins())
        return sorted([
            p.module for p in get_all_plugins()
            if not p.name.startswith('.') and getattr(p, 'visible', True) and p.module in active_plugins
        ])

    def to_internal_value(self, data):
        return {
            'plugins': data
        }

class WritableSerializerMethodField(SerializerMethodField):
    """
    A field that get its representation from calling a method on the
    parent serializer class. The method called will be of the form
    "get_{field_name}", and should take a single argument, which is the
    object being serialized.

    When the field is written, a method of the form "put_{field_name}"
    is called, with the instance and the incoming data as arguments. It
    should return a dictionary of data to be update validated_data with.

    For example:

    class ExampleSerializer(Serializer):
        extra_info = WritableSerializerMethodField()

        def get_extra_info(self, obj):
            return ...  # Calculate some data to return.

        def put_extra_info(self, obj, new_value):
            # Store new value
    """

    def __init__(self, method_name=None, put_method_name=None, **kwargs):
        self.put_method_name = put_method_name
        super().__init__(method_name, **kwargs)
        self.read_only = False

    def bind(self, field_name, parent):
        # The method name defaults to `get_{field_name}`.
        if self.method_name is None:
            self.method_name = f'get_{field_name}'
        if self.put_method_name is None:
            self.put_method_name = f'put_{field_name}'

        super().bind(field_name, parent)

    def to_representation(self, value):
        method = getattr(self.parent, self.method_name)
        return method(value)

    def to_internal_value(self, data):
        method = getattr(self.parent, self.put_method_name)
        return method(self.parent.instance, data)
