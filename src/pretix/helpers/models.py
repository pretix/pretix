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
import copy

from django.core.files import File
from django.db import models


class Thumbnail(models.Model):
    source = models.CharField(max_length=255)
    size = models.CharField(max_length=255)
    thumb = models.FileField(upload_to='pub/thumbs/', max_length=255)
    created = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        unique_together = (('source', 'size'),)


def modelcopy(obj: models.Model, **kwargs):
    n = obj.__class__(**kwargs)
    for f in obj._meta.fields:
        val = getattr(obj, f.name)
        if isinstance(val, (models.Model, File)):
            setattr(n, f.name, copy.copy(val))
        else:
            setattr(n, f.name, copy.deepcopy(val))
    return n
