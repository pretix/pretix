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
from django.utils.translation import gettext_lazy as _
from lxml import etree


def parse(file):
    # Spec: https://www.ebics.de/de/datenformate
    data = file.read()
    root = etree.fromstring(data)

    statements = root.findall("{*}BkToCstmrStmt/{*}Stmt")
    if not statements:
        raise ValueError(_("Empty file or unknown format."))

    def get_text(findall_result):
        if len(findall_result) == 1:
            return findall_result[0].text
        return ""

    rows = []
    for stmt in statements:
        for ntry in stmt.findall("{*}Ntry"):
            minus = ""
            otherparty = "Dbtr"
            if ntry.findall("{*}CdtDbtInd")[0].text == "DBIT":
                otherparty = "Cdtr"
                minus = "-"
            reference_parts = [
                get_text(ntry.findall("{*}NtryDtls/{*}TxDtls/{*}RmtInf/{*}Ustrd")),
                get_text(ntry.findall("{*}NtryDtls/{*}TxDtls/{*}Refs/{*}EndToEndId")),
                get_text(ntry.findall("{*}NtryDtls/{*}TxDtls/{*}Refs/{*}InstructionIdentification")),
            ]
            if ntry.findall("{*}NtryDtls/{*}Btch"):
                # Batch booking, we do not support splitting yet
                reference_parts.insert(0, get_text(ntry.findall("{*}NtryDtls/{*}Btch/{*}PmtInfId")))
            row = {
                'amount': minus + ntry.findall("{*}Amt")[0].text,
                'date': get_text(ntry.findall("{*}BookgDt/{*}Dt")),
                'reference': "\n".join(filter(lambda a: bool(a) and a != "NOTPROVIDED", reference_parts))
            }
            if ext_id := get_text(ntry.findall("{*}AcctSvcrRef")):
                row['external_id'] = ext_id
            if iban := get_text(ntry.findall(f"{{*}}NtryDtls/{{*}}TxDtls/{{*}}RltdPties/{{*}}{otherparty}Acct/{{*}}Id/{{*}}IBAN")):
                row['iban'] = iban
            if bic := get_text(ntry.findall(f"{{*}}NtryDtls/{{*}}TxDtls/{{*}}RltdAgts/{{*}}{otherparty}Agt/{{*}}FinInstnId/{{*}}BICFI")):
                row['bic'] = bic
            if payer := get_text(ntry.findall(f"{{*}}NtryDtls/{{*}}TxDtls/{{*}}RltdPties/{{*}}{otherparty}/{{*}}Nm")):
                row['payer'] = payer
            rows.append(row)

    return rows
