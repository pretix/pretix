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
import csv
import io

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _, gettext_lazy

from pretix.base.i18n import LazyLocaleException


class DataImportError(LazyLocaleException):
    def __init__(self, *args):
        msg = args[0]
        msgargs = args[1] if len(args) > 1 else None
        self.args = args
        if msgargs:
            msg = _(msg) % msgargs
        else:
            msg = _(msg)
        super().__init__(msg)


def parse_csv(file, length=None, mode="strict", charset=None):
    file.seek(0)
    data = file.read(length)
    if not charset:
        try:
            import chardet
            charset = chardet.detect(data)['encoding']
        except ImportError:
            charset = file.charset
    data = data.decode(charset or "utf-8", mode)
    # If the file was modified on a Mac, it only contains \r as line breaks
    if '\r' in data and '\n' not in data:
        data = data.replace('\r', '\n')

    try:
        dialect = csv.Sniffer().sniff(data.split("\n")[0], delimiters=";,.#:")
    except csv.Error:
        return None

    if dialect is None:
        return None

    reader = csv.DictReader(io.StringIO(data), dialect=dialect)
    return reader


class ImportColumn:

    @property
    def identifier(self):
        """
        Unique, internal name of the column.
        """
        raise NotImplementedError

    @property
    def verbose_name(self):
        """
        Human-readable description of the column
        """
        raise NotImplementedError

    @property
    def initial(self):
        """
        Initial value for the form component
        """
        return None

    @property
    def default_value(self):
        """
        Internal default value for the assignment of this column. Defaults to ``empty``. Return ``None`` to disable this
        option.
        """
        return 'empty'

    @property
    def default_label(self):
        """
        Human-readable description of the default assignment of this column, defaults to "Keep empty".
        """
        return gettext_lazy('Keep empty')

    def __init__(self, event):
        self.event = event

    def static_choices(self):
        """
        This will be called when rendering the form component and allows you to return a list of values that can be
        selected by the user statically during import.

        :return: list of 2-tuples of strings
        """
        return []

    def resolve(self, settings, record):
        """
        This method will be called to get the raw value for this field, usually by either using a static value or
        inspecting the CSV file for the assigned header. You usually do not need to implement this on your own,
        the default should be fine.
        """
        k = settings.get(self.identifier, self.default_value)
        if k == self.default_value:
            return None
        elif k.startswith('csv:'):
            return record.get(k[4:], None) or None
        elif k.startswith('static:'):
            return k[7:]
        raise ValidationError(_('Invalid setting for column "{header}".').format(header=self.verbose_name))

    def clean(self, value, previous_values):
        """
        Allows you to validate the raw input value for your column. Raise ``ValidationError`` if the value is invalid.
        You do not need to include the column or row name or value in the error message as it will automatically be
        included.

        :param value: Contains the raw value of your column as returned by ``resolve``. This can usually be ``None``,
                      e.g. if the column is empty or does not exist in this row.
        :param previous_values: Dictionary containing the validated values of all columns that have already been validated.
        """
        return value

    def assign(self, value, obj, **kwargs):
        """
        This will be called to perform the actual import. You are supposed to set attributes on the ``obj`` or other
        related objects that get passed in based on the input ``value``. This is called *before* the actual database
        transaction, so the input objects do not yet have a primary key. If you want to create related objects, you
        need to place them into some sort of internal queue and persist them when ``save`` is called.
        """
        pass

    def save(self, obj):
        """
        This will be called to perform the actual import. This is called inside the actual database transaction and the
        input object ``obj`` has already been saved to the database.
        """
        pass


def i18n_flat(l):
    if isinstance(l.data, dict):
        return l.data.values()
    return [l.data]
