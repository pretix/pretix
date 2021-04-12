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
import codecs
import datetime
import io
from decimal import Decimal

from defusedcsv import csv
from django.core.exceptions import ValidationError
from django.templatetags.l10n import localize
from django.utils.translation import gettext_lazy as _
from localflavor.generic.validators import BICValidator

from pretix.plugins.banktransfer.models import RefundExport


def _get_filename(refund_export):
    return 'bank_transfer_refunds-{}_{}-{}'.format(refund_export.entity_slug, refund_export.datetime.strftime("%Y-%m-%d"), refund_export.id)


def get_refund_export_csv(refund_export: RefundExport):
    byte_data = io.BytesIO()
    StreamWriter = codecs.getwriter('utf-8')
    output = StreamWriter(byte_data)

    writer = csv.writer(output)
    writer.writerow([_("Payer"), "IBAN", "BIC", _("Amount"), _("Currency"), _("Code"), _("Comment")])
    for row in refund_export.rows_data:
        bic = ''
        if row.get('bic'):
            try:
                BICValidator()(row['bic'])
            except ValidationError:
                pass
            else:
                bic = row['bic']
        writer.writerow([
            row['payer'],
            row['iban'],
            bic,
            localize(Decimal(row['amount'])),
            refund_export.currency,
            row['id'],
            row.get('comment') or '',
        ])

    filename = _get_filename(refund_export) + ".csv"
    byte_data.seek(0)
    return filename, 'text/csv', byte_data


from sepaxml import SepaTransfer


def build_sepa_xml(refund_export: RefundExport, account_holder, iban, bic):
    if refund_export.currency != "EUR":
        raise ValueError("Cannot create SEPA export for currency other than EUR.")

    config = {
        "name": account_holder,
        "IBAN": iban,
        "BIC": bic,
        "batch": True,
        "currency": refund_export.currency,
    }
    sepa = SepaTransfer(config, clean=True)

    for row in refund_export.rows_data:
        payment = {
            "name": row['payer'],
            "IBAN": row["iban"],
            "amount": int(Decimal(row['amount']) * 100),  # in euro-cents
            "execution_date": datetime.date.today(),
            "description": f"{row['id']} {refund_export.entity_slug} {_('Refund')} {row.get('comment') or ''}".strip()[:140],
        }
        if row.get('bic'):
            try:
                BICValidator()(row['bic'])
            except ValidationError:
                pass
            else:
                payment['BIC'] = row['bic']

        sepa.add_payment(payment)

    data = sepa.export(validate=True)
    filename = _get_filename(refund_export) + ".xml"
    return filename, 'application/xml', io.BytesIO(data)
