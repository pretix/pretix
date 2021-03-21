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
import re

from django.utils.text import Truncator


class HintMismatchError(Exception):
    pass


def parse(data, hint):
    result = []
    if 'cols' not in hint:
        raise HintMismatchError('Invalid hint')
    if len(data[0]) != hint['cols']:
        raise HintMismatchError('Wrong column count')
    good_hint = False
    for row in data:
        resrow = {}
        if None in row or len(row) != hint['cols']:
            # Wrong column count
            continue
        if hint.get('payer') is not None:
            resrow['payer'] = "\n".join([row[int(i)].strip() for i in hint.get('payer')]).strip()
        if hint.get('reference') is not None:
            resrow['reference'] = "\n".join([row[int(i)].strip() for i in hint.get('reference')]).strip()
        if hint.get('amount') is not None:
            resrow['amount'] = row[int(hint.get('amount'))].strip()
            resrow['amount'] = re.sub('[^0-9,+.-]', '', resrow['amount'])
        if hint.get('date') is not None:
            resrow['date'] = row[int(hint.get('date'))].strip()
        if hint.get('iban') is not None:
            resrow['iban'] = Truncator(row[int(hint.get('iban'))].strip()).chars(200)
        if hint.get('bic') is not None:
            resrow['bic'] = Truncator(row[int(hint.get('bic'))].strip()).chars(200)

        if len(resrow['amount']) == 0 or 'amount' not in resrow or resrow.get('date') == '':
            # This is probably a headline or something other special.
            continue
        if resrow.get('reference') or resrow.get('payer'):
            good_hint = True
        result.append(resrow)
    return result, good_hint


def get_rows_from_file(file):
    data = file.read()
    try:
        import chardet
        charset = chardet.detect(data)['encoding']
    except ImportError:
        charset = file.charset
    data = data.decode(charset or 'utf-8')
    # If the file was modified on a Mac, it only contains \r as line breaks
    if '\r' in data and '\n' not in data:
        data = data.replace('\r', '\n')

    # Sniffing line by line is necessary as some banks like to include
    # one-column garbage at the beginning of the file which breaks the sniffer.
    # See also: http://bugs.python.org/issue2078
    last_e = None
    dialect = None
    for line in data.split("\n"):
        line = line.strip()
        if len(line) == 0:
            continue
        try:
            dialect = csv.Sniffer().sniff(line, delimiters=";,.#:")
        except Exception as e:
            last_e = e
        else:
            last_e = None
            break
    if dialect is None:
        raise last_e or csv.Error("No dialect detected")
    reader = csv.reader(io.StringIO(data), dialect)
    rows = []
    for row in reader:
        if rows and len(row) > len(rows[0]):
            # Some banks put metadata above the real data, things like
            # a headline, the bank's name, the user's name, etc.
            # In many cases, we can identify this because these rows
            # have less columns than the rows containing the real data.
            # Therefore, if the number of columns suddenly grows, we start
            # over with parsing.
            rows = []
        rows.append(row)
    return rows


def new_hint(data):
    return {
        'payer': data.getlist('payer') if 'payer' in data else None,
        'reference': data.getlist('reference') if 'reference' in data else None,
        'date': int(data.get('date')) if 'date' in data else None,
        'amount': int(data.get('amount')) if 'amount' in data else None,
        'cols': int(data.get('cols')) if 'cols' in data else None,
        'iban': int(data.get('iban')) if 'iban' in data else None,
        'bic': int(data.get('bic')) if 'bic' in data else None,
    }
