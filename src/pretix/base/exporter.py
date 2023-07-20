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
# This file contains Apache-licensed contributions copyrighted by: Jakob Schnell, Jonas Große Sundrup, Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import io
import tempfile
from collections import OrderedDict, namedtuple
from decimal import Decimal
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from defusedcsv import csv
from django import forms
from django.conf import settings
from django.db.models import QuerySet
from django.utils.formats import localize
from django.utils.translation import gettext, gettext_lazy as _

from pretix.base.models import Event
from pretix.helpers.safe_openpyxl import (  # NOQA: backwards compatibility for plugins using excel_safe
    SafeWorkbook, remove_invalid_excel_chars as excel_safe,
)

__ = excel_safe  # just so the compatibility import above is "used" and doesn't get removed by linter


class BaseExporter:
    """
    This is the base class for all data exporters
    """

    def __init__(self, event, organizer, progress_callback=lambda v: None):
        self.event = event
        self.organizer = organizer
        self.progress_callback = progress_callback
        self.is_multievent = isinstance(event, QuerySet)
        if isinstance(event, QuerySet):
            self.events = event
            self.event = None
            e = self.events.first()
            self.timezone = e.timezone if e else ZoneInfo(settings.TIME_ZONE)
        else:
            self.events = Event.objects.filter(pk=event.pk)
            self.timezone = event.timezone

    def __str__(self):
        return self.identifier

    @property
    def verbose_name(self) -> str:
        """
        A human-readable name for this exporter. This should be short but
        self-explaining. Good examples include 'Orders as JSON' or 'Orders as Microsoft Excel'.
        """
        raise NotImplementedError()  # NOQA

    @property
    def description(self) -> str:
        """
        A description for this exporter.
        """
        return ""

    @property
    def category(self) -> Optional[str]:
        """
        A category name for this exporter, or ``None``.
        """
        return None

    @property
    def featured(self) -> bool:
        """
        If ``True``, this exporter will be highlighted.
        """
        return False

    @property
    def identifier(self) -> str:
        """
        A short and unique identifier for this exporter.
        This should only contain lowercase letters and in most
        cases will be the same as your package name.
        """
        raise NotImplementedError()  # NOQA

    @property
    def export_form_fields(self) -> dict:
        """
        When the event's administrator visits the export page, this method
        is called to return the configuration fields available.

        It should therefore return a dictionary where the keys should be field names and
        the values should be corresponding Django form fields.

        We suggest that you return an ``OrderedDict`` object instead of a dictionary.
        Your implementation could look like this::

            @property
            def export_form_fields(self):
                return OrderedDict(
                    [
                        ('tab_width',
                         forms.IntegerField(
                             label=_('Tab width'),
                             default=4
                         ))
                    ]
                )
        """
        return {}

    def render(self, form_data: dict) -> Tuple[str, str, Optional[bytes]]:
        """
        Render the exported file and return a tuple consisting of a filename, a file type
        and file content.

        :type form_data: dict
        :param form_data: The form data of the export details form
        :param output_file: You can optionally accept a parameter that will be given a file handle to write the
                            output to. In this case, you can return None instead of the file content.

        Note: If you use a ``ModelChoiceField`` (or a ``ModelMultipleChoiceField``), the
        ``form_data`` will not contain the model instance but only it's primary key (or
        a list of primary keys) for reasons of internal serialization when using background
        tasks.
        """
        raise NotImplementedError()  # NOQA

    def available_for_user(self, user) -> bool:
        """
        Allows to do additional checks whether an exporter is available based on the user who calls it. Note that
        ``user`` may be ``None`` e.g. during API usage.
        """
        return True


class OrganizerLevelExportMixin:
    @property
    def organizer_required_permission(self) -> str:
        """
        The permission level required to use this exporter. Only useful for organizer-level exports,
        not for event-level exports.
        """
        return 'can_view_orders'


class ListExporter(BaseExporter):
    ProgressSetTotal = namedtuple('ProgressSetTotal', 'total')

    @property
    def export_form_fields(self) -> dict:
        ff = OrderedDict(
            [
                ('_format',
                 forms.ChoiceField(
                     label=_('Export format'),
                     choices=(
                         ('xlsx', _('Excel (.xlsx)')),
                         ('default', _('CSV (with commas)')),
                         ('csv-excel', _('CSV (Excel-style)')),
                         ('semicolon', _('CSV (with semicolons)')),
                     ),
                 )),
            ]
        )
        ff.update(self.additional_form_fields)
        return ff

    @property
    def additional_form_fields(self) -> dict:
        return {}

    def iterate_list(self, form_data):
        raise NotImplementedError()  # noqa

    def get_filename(self):
        return 'export'

    def _render_csv(self, form_data, output_file=None, **kwargs):
        if output_file:
            if 'b' in output_file.mode:
                output_file = io.TextIOWrapper(output_file, encoding='utf-8', newline='')
            writer = csv.writer(output_file, **kwargs)
            total = 0
            counter = 0
            for line in self.iterate_list(form_data):
                if isinstance(line, self.ProgressSetTotal):
                    total = line.total
                    continue
                line = [
                    localize(f) if isinstance(f, Decimal) else f
                    for f in line
                ]
                if total:
                    counter += 1
                    if counter % max(10, total // 100) == 0:
                        self.progress_callback(counter / total * 100)
                writer.writerow(line)
            return self.get_filename() + '.csv', 'text/csv', None
        else:
            output = io.StringIO()
            writer = csv.writer(output, **kwargs)
            total = 0
            counter = 0
            for line in self.iterate_list(form_data):
                if isinstance(line, self.ProgressSetTotal):
                    total = line.total
                    continue
                line = [
                    localize(f) if isinstance(f, Decimal) else f
                    for f in line
                ]
                if total:
                    counter += 1
                    if counter % max(10, total // 100) == 0:
                        self.progress_callback(counter / total * 100)
                writer.writerow(line)
            return self.get_filename() + '.csv', 'text/csv', output.getvalue().encode("utf-8")

    def prepare_xlsx_sheet(self, ws):
        pass

    def _render_xlsx(self, form_data, output_file=None):
        wb = SafeWorkbook(write_only=True)
        ws = wb.create_sheet()
        self.prepare_xlsx_sheet(ws)
        try:
            ws.title = str(self.verbose_name)
        except:
            pass
        total = 0
        counter = 0
        for i, line in enumerate(self.iterate_list(form_data)):
            if isinstance(line, self.ProgressSetTotal):
                total = line.total
                continue
            ws.append([
                val for val in line
            ])
            if total:
                counter += 1
                if counter % max(10, total // 100) == 0:
                    self.progress_callback(counter / total * 100)

        if output_file:
            wb.save(output_file)
            return self.get_filename() + '.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', None
        else:
            with tempfile.NamedTemporaryFile(suffix='.xlsx') as f:
                wb.save(f.name)
                f.seek(0)
                return self.get_filename() + '.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', f.read()

    def render(self, form_data: dict, output_file=None) -> Tuple[str, str, bytes]:
        if form_data.get('_format') == 'xlsx':
            return self._render_xlsx(form_data, output_file=output_file)
        elif form_data.get('_format') == 'default':
            return self._render_csv(form_data, quoting=csv.QUOTE_NONNUMERIC, delimiter=',', output_file=output_file)
        elif form_data.get('_format') == 'csv-excel':
            return self._render_csv(form_data, dialect='excel', output_file=output_file)
        elif form_data.get('_format') == 'semicolon':
            return self._render_csv(form_data, dialect='excel', delimiter=';', output_file=output_file)


class MultiSheetListExporter(ListExporter):

    @property
    def sheets(self):
        raise NotImplementedError()

    @property
    def export_form_fields(self) -> dict:
        choices = [
            ('xlsx', _('Combined Excel (.xlsx)')),
        ]
        for s, l in self.sheets:
            choices += [
                (s + ':default', str(l) + ' – ' + gettext('CSV (with commas)')),
                (s + ':excel', str(l) + ' – ' + gettext('CSV (Excel-style)')),
                (s + ':semicolon', str(l) + ' – ' + gettext('CSV (with semicolons)')),
            ]
        ff = OrderedDict(
            [
                ('_format',
                 forms.ChoiceField(
                     label=_('Export format'),
                     choices=choices,
                 )),
            ]
        )
        ff.update(self.additional_form_fields)
        return ff

    def iterate_list(self, form_data):
        pass

    def iterate_sheet(self, form_data, sheet):
        if hasattr(self, 'iterate_' + sheet):
            yield from getattr(self, 'iterate_' + sheet)(form_data)
        else:
            raise NotImplementedError()  # noqa

    def _render_sheet_csv(self, form_data, sheet, output_file=None, **kwargs):
        total = 0
        counter = 0
        if output_file:
            if 'b' in output_file.mode:
                output_file = io.TextIOWrapper(output_file, encoding='utf-8', newline='')
            writer = csv.writer(output_file, **kwargs)
            for line in self.iterate_sheet(form_data, sheet):
                if isinstance(line, self.ProgressSetTotal):
                    total = line.total
                    continue
                line = [
                    localize(f) if isinstance(f, Decimal) else f
                    for f in line
                ]
                writer.writerow(line)
                if total:
                    counter += 1
                    if counter % max(10, total // 100) == 0:
                        self.progress_callback(counter / total * 100)
            return self.get_filename() + '.csv', 'text/csv', None
        else:
            output = io.StringIO()
            writer = csv.writer(output, **kwargs)
            for line in self.iterate_sheet(form_data, sheet):
                if isinstance(line, self.ProgressSetTotal):
                    total = line.total
                    continue
                line = [
                    localize(f) if isinstance(f, Decimal) else f
                    for f in line
                ]
                writer.writerow(line)
                if total:
                    counter += 1
                    if counter % max(10, total // 100) == 0:
                        self.progress_callback(counter / total * 100)
            return self.get_filename() + '.csv', 'text/csv', output.getvalue().encode("utf-8")

    def _render_xlsx(self, form_data, output_file=None):
        wb = SafeWorkbook(write_only=True)
        n_sheets = len(self.sheets)
        for i_sheet, (s, l) in enumerate(self.sheets):
            ws = wb.create_sheet(str(l))
            if hasattr(self, 'prepare_xlsx_sheet_' + s):
                getattr(self, 'prepare_xlsx_sheet_' + s)(ws)

            total = 0
            counter = 0
            for i, line in enumerate(self.iterate_sheet(form_data, sheet=s)):
                if isinstance(line, self.ProgressSetTotal):
                    total = line.total
                    continue
                ws.append([
                    val for val in line
                ])
                if total:
                    counter += 1
                    if counter % max(10, total // 100) == 0:
                        self.progress_callback(counter / total * 100 / n_sheets + 100 / n_sheets * i_sheet)

        if output_file:
            wb.save(output_file)
            return self.get_filename() + '.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', None
        else:
            with tempfile.NamedTemporaryFile(suffix='.xlsx') as f:
                wb.save(f.name)
                f.seek(0)
                return self.get_filename() + '.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', f.read()

    def render(self, form_data: dict, output_file=None) -> Tuple[str, str, bytes]:
        if form_data.get('_format') == 'xlsx':
            return self._render_xlsx(form_data, output_file=output_file)
        elif ':' in form_data.get('_format'):
            sheet, f = form_data.get('_format').split(':')
            if f == 'default':
                return self._render_sheet_csv(form_data, sheet, quoting=csv.QUOTE_NONNUMERIC, delimiter=',',
                                              output_file=output_file)
            elif f == 'excel':
                return self._render_sheet_csv(form_data, sheet, dialect='excel', output_file=output_file)
            elif f == 'semicolon':
                return self._render_sheet_csv(form_data, sheet, dialect='excel', delimiter=';', output_file=output_file)
