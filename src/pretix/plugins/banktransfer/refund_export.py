import codecs
import datetime
import io
from decimal import Decimal

from defusedcsv import csv
from django.templatetags.l10n import localize
from django.utils.translation import gettext_lazy as _

from pretix.plugins.banktransfer.models import RefundExport


def _get_filename(refund_export):
    return 'bank_transfer_refunds-{}_{}-{}'.format(refund_export.entity_slug, refund_export.datetime.strftime("%Y-%m-%d"), refund_export.id)


def get_refund_export_csv(refund_export: RefundExport):
    byte_data = io.BytesIO()
    StreamWriter = codecs.getwriter('utf-8')
    output = StreamWriter(byte_data)

    writer = csv.writer(output)
    writer.writerow([_("Payer"), "IBAN", "BIC", _("Amount"), _("Currency"), _("Code")])
    for row in refund_export.rows_data:
        writer.writerow([
            row['payer'],
            row['iban'],
            row['bic'],
            localize(Decimal(row['amount'])),
            refund_export.currency,
            row['id'],
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
            "BIC": row["bic"],
            "amount": int(Decimal(row['amount']) * 100),  # in euro-cents
            "execution_date": datetime.date.today(),
            "description": f"{_('Refund')} {refund_export.entity_slug} {row['id']}",
        }
        sepa.add_payment(payment)

    data = sepa.export(validate=True)
    filename = _get_filename(refund_export) + ".xml"
    return filename, 'application/xml', io.BytesIO(data)
