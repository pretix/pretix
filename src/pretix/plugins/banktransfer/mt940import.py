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
# This file contains Apache-licensed contributions copyrighted by: Claudio Luck
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import io
import string

import mt940

from pretix.base.decimal import round_decimal

"""
The parse_transaction_details and join_reference functions are
Copyright (c) 2017 Nicole Klünder

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def parse_transaction_details(raw_data):
    transaction_details = {
        'code': [raw_data[:3]],
    }

    code_mapping = {
        '00': 'description',
        '10': 'primanota',
        '30': 'blz',
        '31': 'accountnumber',
        '32': 'accountholder',
        '33': 'accountholder',
        '34': 'chargeback',
        '35': 'recipient',
        '36': 'recipient',
    }
    for i in range(20, 30):
        code_mapping[str(i)] = 'reference'
    for i in range(60, 64):
        code_mapping[str(i)] = 'additional'

    delimiter = raw_data[3]

    lines = sorted((line[:2], line[2:].strip()) for line in raw_data.split(delimiter)[1:])
    for code, data in lines:
        transaction_details.setdefault(code_mapping.get(code, code), []).append(data)

    transaction_details = {name: '\n'.join(elems) for name, elems in transaction_details.items()}

    if 'reference' in transaction_details:
        fragments = {'': []}
        current_code = ''
        for line in transaction_details['reference'].split('\n'):
            code = line.split('+', 1)[0]
            if code in ('EREF', 'SVWZ'):
                current_code = code
                line = line[len(code) + 1:]
            fragments.setdefault(current_code, []).append(line)

        fragments = {code: '\n'.join(elems) for code, elems in fragments.items()}

        if 'EREF' in fragments:
            transaction_details['eref'] = fragments['EREF'].replace('\n', '')

        if 'SVWZ' in fragments:
            transaction_details['reference'] = fragments['SVWZ']

    return transaction_details


def join_reference(reference_list, payer):
    # Join Reference into one line.
    reference = ''
    if reference_list and ''.join(reference_list):
        reference += reference_list.pop(0)
        for d in reference_list:
            if not d:
                continue
            if not (
                (reference[-1] in string.ascii_lowercase and d[0] in string.ascii_lowercase) or
                (reference[-1] in string.ascii_uppercase and d[0] in string.ascii_uppercase) or
                (reference[-1] in string.digits + string.ascii_uppercase and d[0] in ('-', ':')) or
                (reference[-1] == ' ' or d[0] == ' ')
            ):
                reference += ' '
            reference += d
    reference = [s for s in reference.split(' ') if s]

    eref = ''
    if len(reference) >= 2 and reference[-2] == 'ABWA:':
        payer['abwa'] = reference[-1]
        reference = reference[:-2]
    elif len(reference) >= 3 and reference[-3] == 'ABWA:':
        payer['abwa'] = ''.join(reference[-2:])
        reference = reference[:-3]

    if len(reference) >= 2 and reference[-2] == 'BIC:':
        payer['bic'] = reference[-1]
        reference = reference[:-2]
    elif len(reference) >= 3 and reference[-3] == 'BIC:':
        payer['bic'] = ''.join(reference[-2:])
        reference = reference[:-3]

    if len(reference) >= 2 and reference[-2] == 'IBAN:':
        payer['iban'] = reference[-1]
        reference = reference[:-2]
    elif len(reference) >= 3 and reference[-3] == 'IBAN:':
        payer['iban'] = ''.join(reference[-2:])
        reference = reference[:-3]

    reference = ' '.join(reference)

    if ' EREF: ' in reference:
        reference = reference.split(' EREF: ')
        eref = reference[-1]
        reference = reference[:-1]
        reference = ' EREF: '.join(reference)

    return reference, eref


def parse(file):
    data = file.read()
    try:
        import chardet

        charset = chardet.detect(data)['encoding']
    except ImportError:
        charset = file.charset
    data = data.decode(charset or 'utf-8')
    mt = mt940.parse(io.StringIO(data.strip()))
    result = []
    for t in mt:
        td = t.data.get('transaction_details', '')
        if len(td) >= 4 and td[3] == '?':
            # SEPA content
            transaction_details = parse_transaction_details(td.replace("\n", ""))

            payer = {
                'name': transaction_details.get('accountholder', '') or t.data.get('applicant_name', ''),
                # In reality, these fields are sometimes IBANs and BICs, and sometimes legacy numbers. We don't
                # really know (except for a syntax check) which will be performed anyways much later in the stack.
                'iban': transaction_details.get('accountnumber', '') or t.data.get('applicant_iban', ''),
                'bic': transaction_details.get('blz', '') or t.data.get('applicant_bin', ''),
            }
            reference, eref = join_reference(transaction_details.get('reference', '').split('\n'), payer)
            if not eref:
                eref = transaction_details.get('eref', '')

            result.append({
                'amount': str(round_decimal(t.data['amount'].amount)),
                'reference': reference + (' EREF: {}'.format(eref) if eref else ''),
                'payer': payer['name'].strip(),
                'date': t.data['date'].isoformat(),
                **{k: payer[k].strip() for k in ("iban", "bic") if payer.get(k)}
            })
        else:
            payer = {
                'payer': t.data.get('applicant_name', ''),
                # In reality, these fields are sometimes IBANs and BICs, and sometimes legacy numbers. We don't
                # really know (except for a syntax check) which will be performed anyways much later in the stack.
                'iban': t.data.get('applicant_iban', ''),
                'bic': t.data.get('applicant_bin', ''),
            }
            result.append({
                'reference': "\n".join([
                    t.data.get(f) for f in ('transaction_details', 'customer_reference', 'bank_reference', 'purpose',
                                            'extra_details', 'non_swift_text') if t.data.get(f, '')]),
                'amount': str(round_decimal(t.data['amount'].amount)),
                'date': t.data['date'].isoformat(),
                **{k: payer[k].strip() for k in ("iban", "bic", "payer") if payer.get(k)}
            })
    return result
