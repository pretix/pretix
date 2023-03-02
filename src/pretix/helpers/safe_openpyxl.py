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
import re
import types
from inspect import isgenerator

from openpyxl import Workbook
from openpyxl.cell.cell import (
    KNOWN_TYPES, TIME_TYPES, TYPE_FORMULA, TYPE_STRING, Cell,
)
from openpyxl.compat import NUMERIC_TYPES
from openpyxl.utils import column_index_from_string
from openpyxl.utils.exceptions import ReadOnlyWorkbookException
from openpyxl.worksheet._write_only import WriteOnlyWorksheet
from openpyxl.worksheet.worksheet import Worksheet

SAFE_TYPES = NUMERIC_TYPES + TIME_TYPES + (bool, type(None))


"""
This module provides a safer version of openpyxl's `Workbook` class to generate XLSX files from
user-generated data using `WriteOnlyWorksheet` and `ws.append()`. We commonly use these methods
to output e.g. order data, which contains data from untrusted sources such as attendee names.

There are mainly two problems this solves:

- It makes sure strings starting with = are treated as text, not as a formula, as openpyxl will
  otherwise assume, which can be used for remote code execution.

- It removes characters considered invalid by Excel to avoid exporter crashes.
"""

ILLEGAL_CHARACTERS_RE = re.compile(
    # From the XML specification
    # Char ::= #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]
    r'[^\u0020-\uD7FF\u0009\u000A\u000D\uE000-\uFFFD\U00010000-\U0010FFFF]'
)


def remove_invalid_excel_chars(val):
    if isinstance(val, Cell):
        return val

    if not isinstance(val, KNOWN_TYPES):
        val = str(val)

    if isinstance(val, bytes):
        val = val.decode("utf-8", errors="ignore")

    if isinstance(val, str):
        val = re.sub(ILLEGAL_CHARACTERS_RE, '', val)

    return val


def SafeCell(*args, value=None, **kwargs):
    value = remove_invalid_excel_chars(value)
    c = Cell(*args, value=value, **kwargs)
    if c.data_type == TYPE_FORMULA:
        c.data_type = TYPE_STRING
    return c


class SafeWriteOnlyWorksheet(WriteOnlyWorksheet):
    def append(self, row):
        if not isgenerator(row) and not isinstance(row, (list, tuple, range)):
            self._invalid_row(row)

        self._get_writer()

        if self._rows is None:
            self._rows = self._write_rows()
            next(self._rows)

        filtered_row = []
        for content in row:
            if isinstance(content, Cell):
                filtered_row.append(content)
            else:
                filtered_row.append(
                    SafeCell(self, row=1, column=1, value=remove_invalid_excel_chars(content))
                )

        self._rows.send(filtered_row)


class SafeWorksheet(Worksheet):
    def append(self, iterable):
        row_idx = self._current_row + 1

        if isinstance(iterable, (list, tuple, range)) or isgenerator(iterable):
            for col_idx, content in enumerate(iterable, 1):
                if isinstance(content, Cell):
                    # compatible with write-only mode
                    cell = content
                    if cell.parent and cell.parent != self:
                        raise ValueError("Cells cannot be copied from other worksheets")
                    cell.parent = self
                    cell.column = col_idx
                    cell.row = row_idx
                else:
                    cell = SafeCell(self, row=row_idx, column=col_idx, value=remove_invalid_excel_chars(content))
                self._cells[(row_idx, col_idx)] = cell

        elif isinstance(iterable, dict):
            for col_idx, content in iterable.items():
                if isinstance(col_idx, str):
                    col_idx = column_index_from_string(col_idx)
                cell = SafeCell(self, row=row_idx, column=col_idx, value=content)
                self._cells[(row_idx, col_idx)] = cell

        else:
            self._invalid_row(iterable)

        self._current_row = row_idx


class SafeWorkbook(Workbook):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._sheets:
            # monkeypatch existing sheets
            for s in self._sheets:
                if self.write_only:
                    s.append = types.MethodType(SafeWriteOnlyWorksheet.append, s)
                else:
                    s.append = types.MethodType(SafeWorksheet.append, s)

    def create_sheet(self, title=None, index=None):
        if self.read_only:
            raise ReadOnlyWorkbookException('Cannot create new sheet in a read-only workbook')

        if self.write_only:
            new_ws = SafeWriteOnlyWorksheet(parent=self, title=title)
        else:
            new_ws = SafeWorksheet(parent=self, title=title)

        self._add_sheet(sheet=new_ws, index=index)
        return new_ws
