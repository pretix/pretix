#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
from urllib.parse import quote, urlencode

import text_unidecode
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _


def dotdecimal(value):
    return str(value).replace(",", ".")


def commadecimal(value):
    return str(value).replace(".", ",")


def generate_payment_qr_codes(
        event,
        code,
        amount,
        bank_details_sepa_bic,
        bank_details_sepa_name,
        bank_details_sepa_iban,
):
    out = []
    for method in [
        swiss_qrbill,
        czech_spayd,
        euro_epc_qr,
        euro_bezahlcode,
    ]:
        data = method(
            event,
            code,
            amount,
            bank_details_sepa_bic,
            bank_details_sepa_name,
            bank_details_sepa_iban,
        )
        if data:
            out.append(data)

    return out


def euro_epc_qr(
        event,
        code,
        amount,
        bank_details_sepa_bic,
        bank_details_sepa_name,
        bank_details_sepa_iban,
):
    if event.currency != 'EUR' or not bank_details_sepa_iban:
        return

    return {
        "id": "girocode",
        "label": "EPC-QR",
        "qr_data": "\n".join(text_unidecode.unidecode(str(d or '')) for d in [
            "BCD",   # Service Tag: ‘BCD’
            "002",   # Version: V2
            "2",     # Character set: ISO 8859-1
            "SCT",   # Identification code: ‘SCT‘
            bank_details_sepa_bic,   # AT-23 BIC of the Beneficiary Bank
            bank_details_sepa_name,  # AT-21 Name of the Beneficiary
            bank_details_sepa_iban,  # AT-20 Account number of the Beneficiary
            f"{event.currency}{dotdecimal(amount)}",  # AT-04 Amount of the Credit Transfer in Euro
            "",      # AT-44 Purpose of the Credit Transfer
            "",      # AT-05 Remittance Information (Structured)
            code,    # AT-05 Remittance Information (Unstructured)
            "",      # Beneficiary to originator information
            "",
        ]),
    }


def euro_bezahlcode(
        event,
        code,
        amount,
        bank_details_sepa_bic,
        bank_details_sepa_name,
        bank_details_sepa_iban,
):
    if not bank_details_sepa_iban or bank_details_sepa_iban[:2] != 'DE':
        return
    if event.currency != 'EUR':
        return

    qr_data = "bank://singlepaymentsepa?" + urlencode({
        "name": str(bank_details_sepa_name),
        "iban": str(bank_details_sepa_iban),
        "bic": str(bank_details_sepa_bic),
        "amount": commadecimal(amount),
        "reason": str(code),
        "currency": str(event.currency),
    }, quote_via=quote)
    return {
        "id": "bezahlcode",
        "label": "BezahlCode",
        "qr_data": mark_safe(qr_data),
        "link": qr_data,
        "link_aria_label": _("Open BezahlCode in your banking app to start the payment process."),
    }


def swiss_qrbill(
        event,
        code,
        amount,
        bank_details_sepa_bic,
        bank_details_sepa_name,
        bank_details_sepa_iban,
):
    if not bank_details_sepa_iban or not bank_details_sepa_iban[:2] in ('CH', 'LI'):
        return
    if event.currency not in ('EUR', 'CHF'):
        return
    if not event.settings.invoice_address_from or not event.settings.invoice_address_from_country:
        return

    data_fields = [
        'SPC',
        '0200',
        '1',
        bank_details_sepa_iban,
        'K',
        bank_details_sepa_name[:70],
        event.settings.invoice_address_from.replace('\n', ', ')[:70],
        (event.settings.invoice_address_from_zipcode + ' ' + event.settings.invoice_address_from_city)[:70],
        '',
        '',
        str(event.settings.invoice_address_from_country),
        '',  # rfu
        '',  # rfu
        '',  # rfu
        '',  # rfu
        '',  # rfu
        '',  # rfu
        '',  # rfu
        str(amount),
        event.currency,
        '',  # debtor address
        '',  # debtor address
        '',  # debtor address
        '',  # debtor address
        '',  # debtor address
        '',  # debtor address
        '',  # debtor address
        'NON',
        '',  # structured reference
        code,
        'EPD',
    ]

    data_fields = [text_unidecode.unidecode(d or '') for d in data_fields]
    qr_data = '\r\n'.join(data_fields)
    return {
        "id": "qrbill",
        "label": "QR-bill",
        "html_prefix": mark_safe(
            '<svg class="banktransfer-swiss-cross" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 19.8 19.8">'
            '<path stroke="#fff" stroke-width="1.436" d="M.7.7h18.4v18.4H.7z"/><path fill="#fff" d="M8.3 4h3.3v11H8.3z"/>'
            '<path fill="#fff" d="M4.4 7.9h11v3.3h-11z"/></svg>'
        ),
        "qr_data": qr_data,
        "css_class": "banktransfer-swiss-cross-overlay",
    }


def czech_spayd(
        event,
        code,
        amount,
        bank_details_sepa_bic,
        bank_details_sepa_name,
        bank_details_sepa_iban,
):
    if not bank_details_sepa_iban or not bank_details_sepa_iban[:2] in ('CZ', 'SK'):
        return
    if event.currency not in ('EUR', 'CZK'):
        return

    qr_data = f"SPD*1.0*ACC:{bank_details_sepa_iban}*AM:{dotdecimal(amount)}*CC:{event.currency}*MSG:{code}"
    return {
        "id": "spayd",
        "label": "SPAYD",
        "qr_data": qr_data,
    }
