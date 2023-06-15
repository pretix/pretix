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
"""
Django, for theoretically very valid reasons, creates migrations for *every single thing*
we change on a model. Even the `help_text`! This makes sense, as we don't know if any
database backend unknown to us might actually use this information for its database schema.

However, pretix only supports PostgreSQL and SQLite and we can be pretty
certain that some changes to models will never require a change to the database. In this case,
not creating a migration for certain changes will save us some performance while applying them
*and* allow for a cleaner git history. Win-win!

Only caveat is that we need to do some dirty monkeypatching to achieve it...
"""
from django.db import models
from django.db.migrations.operations import models as modelops
from django_countries.fields import CountryField


def monkeypatch_migrations():
    modelops.AlterModelOptions.ALTER_OPTION_KEYS.remove("verbose_name")
    modelops.AlterModelOptions.ALTER_OPTION_KEYS.remove("verbose_name_plural")
    modelops.AlterModelOptions.ALTER_OPTION_KEYS.remove("ordering")
    modelops.AlterModelOptions.ALTER_OPTION_KEYS.remove("get_latest_by")
    modelops.AlterModelOptions.ALTER_OPTION_KEYS.remove("default_manager_name")
    modelops.AlterModelOptions.ALTER_OPTION_KEYS.remove("permissions")
    modelops.AlterModelOptions.ALTER_OPTION_KEYS.remove("default_permissions")
    IGNORED_ATTRS = [
        # (field type, attribute name, banlist of field sub-types)
        (models.Field, 'verbose_name', []),
        (models.Field, 'help_text', []),
        (models.Field, 'validators', []),
        (models.Field, 'editable', [models.DateField, models.DateTimeField, models.DateField, models.BinaryField]),
        (models.Field, 'blank', [models.DateField, models.DateTimeField, models.AutoField, models.NullBooleanField,
                                 models.TimeField]),
        (models.CharField, 'choices', [CountryField])
    ]

    original_deconstruct = models.Field.deconstruct

    def new_deconstruct(self):
        name, path, args, kwargs = original_deconstruct(self)
        for ftype, attr, banlist in IGNORED_ATTRS:
            if isinstance(self, ftype) and not any(isinstance(self, ft) for ft in banlist):
                kwargs.pop(attr, None)
        return name, path, args, kwargs

    models.Field.deconstruct = new_deconstruct
