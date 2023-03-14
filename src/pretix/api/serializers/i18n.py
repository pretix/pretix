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
from django.conf import settings
from django.core.validators import URLValidator
from i18nfield.fields import I18nCharField, I18nTextField
from i18nfield.strings import LazyI18nString
from rest_framework.exceptions import ValidationError
from rest_framework.fields import Field
from rest_framework.serializers import ModelSerializer


class I18nField(Field):
    def __init__(self, **kwargs):
        self.allow_blank = kwargs.pop('allow_blank', False)
        self.trim_whitespace = kwargs.pop('trim_whitespace', True)
        self.max_length = kwargs.pop('max_length', None)
        self.min_length = kwargs.pop('min_length', None)
        super().__init__(**kwargs)

    def to_representation(self, value):
        if hasattr(value, 'data'):
            if isinstance(value.data, dict):
                return value.data
            elif value.data is None:
                return None
            else:
                return {
                    settings.LANGUAGE_CODE: str(value.data)
                }
        elif value is None:
            return None
        else:
            return {
                settings.LANGUAGE_CODE: str(value)
            }

    def to_internal_value(self, data):
        if isinstance(data, str):
            return LazyI18nString(data)
        elif isinstance(data, dict):
            if any([k not in dict(settings.LANGUAGES) for k in data.keys()]):
                raise ValidationError('Invalid languages included.')
            return LazyI18nString(data)
        else:
            raise ValidationError('Invalid data type.')


class I18nAwareModelSerializer(ModelSerializer):
    pass


I18nAwareModelSerializer.serializer_field_mapping[I18nCharField] = I18nField
I18nAwareModelSerializer.serializer_field_mapping[I18nTextField] = I18nField


class I18nURLField(I18nField):
    def to_internal_value(self, value):
        value = super().to_internal_value(value)
        if not value:
            return value
        if isinstance(value.data, dict):
            for v in value.data.values():
                if v:
                    URLValidator()(v)
        else:
            URLValidator()(value.data)
        return value
