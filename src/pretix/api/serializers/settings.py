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
import logging

from django.core.files import File
from django.core.files.storage import default_storage
from django.db.models.fields.files import FieldFile
from hierarkey.proxy import HierarkeyProxy
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from pretix.api.serializers.fields import UploadedFileField
from pretix.base.settings import DEFAULTS

logger = logging.getLogger(__name__)


class SettingsSerializer(serializers.Serializer):
    default_fields = []
    readonly_fields = []

    def __init__(self, *args, **kwargs):
        self.changed_data = []
        super().__init__(*args, **kwargs)
        for fname in self.default_fields:
            kwargs = DEFAULTS[fname].get('serializer_kwargs', {})
            if callable(kwargs):
                kwargs = kwargs()
            kwargs.setdefault('required', False)
            kwargs.setdefault('allow_null', True)
            form_kwargs = DEFAULTS[fname].get('form_kwargs', {})
            if callable(form_kwargs):
                form_kwargs = form_kwargs()
            if 'serializer_class' not in DEFAULTS[fname]:
                raise ValidationError('{} has no serializer class'.format(fname))
            f = DEFAULTS[fname]['serializer_class'](
                **kwargs
            )
            f._label = str(form_kwargs.get('label', fname))
            f._help_text = str(form_kwargs.get('help_text'))
            f.parent = self
            self.fields[fname] = f

    def validate(self, attrs):
        return {k: v for k, v in attrs.items() if k not in self.readonly_fields}

    def update(self, instance: HierarkeyProxy, validated_data):
        for attr, value in validated_data.items():
            if attr in self.readonly_fields:
                continue
            if isinstance(value, FieldFile):
                # Delete old file
                fname = instance.get(attr, as_type=File)
                if fname:
                    try:
                        default_storage.delete(fname.name)
                    except OSError:  # pragma: no cover
                        logger.error('Deleting file %s failed.' % fname.name)

                # Create new file
                newname = default_storage.save(self.get_new_filename(value.name), value)
                instance.set(attr, File(file=value, name=newname))
                self.changed_data.append(attr)
            elif isinstance(self.fields[attr], UploadedFileField):
                if value is None:
                    fname = instance.get(attr, as_type=File)
                    if fname:
                        try:
                            default_storage.delete(fname.name)
                        except OSError:  # pragma: no cover
                            logger.error('Deleting file %s failed.' % fname.name)
                    instance.delete(attr)
                else:
                    # file is unchanged
                    continue
            elif value is None:
                instance.delete(attr)
                self.changed_data.append(attr)
            elif instance.get(attr, as_type=type(value)) != value:
                instance.set(attr, value)
                self.changed_data.append(attr)
        return instance

    def get_new_filename(self, name: str) -> str:
        raise NotImplementedError()
