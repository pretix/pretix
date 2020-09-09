import codecs
import io
from decimal import Decimal

from defusedcsv import csv
from django.templatetags.l10n import localize
from django.utils.translation import gettext_lazy as _

from pretix.plugins.banktransfer.models import RefundExport


def get_refund_export(refund_export: RefundExport):
    if refund_export.organizer:
        currency = refund_export.organizer.events.first().currency
        slug = refund_export.organizer.slug
    else:
        currency = refund_export.event.currency
        slug = refund_export.event.slug

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
            currency,
            row['id'],
        ])

    filename = 'bank_transfer_refunds-{}_{}-{}.csv'.format(slug, refund_export.datetime.strftime("%Y-%m-%d"), refund_export.id)
    byte_data.seek(0)
    return filename, 'text/csv', byte_data
