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
import os.path

from django.test import TestCase

from pretix.plugins.banktransfer import camtimport

DATA_DIR = os.path.dirname(__file__)


class CamtImportTest(TestCase):
    def _test_from_sample_file(self, filename, expected_parsed):
        with open(os.path.join(DATA_DIR, filename), "rb") as f:
            parsed = camtimport.parse(f)
            print(parsed)
            self.assertEqual(parsed, expected_parsed)

    def test_sample_file_sepatools(self):
        expected_parsed = [
            {
                "amount": "-2.00",
                "date": "2013-12-27",
                "reference": "TEST BERWEISUNG MITTELS BLZUND KONTONUMMER - DTA",
                "external_id": "2013122710583450000",
                "payer": "Testkonto Nummer 2",
            },
            {
                "amount": "-3.00",
                "date": "2013-12-27",
                "reference": "Test+berweisung mit BIC und IBAN SEPA IBAN: DE58740618130100033626 BIC: GENODEF1PFK",
                "external_id": "2013122710583600000",
                "iban": "DE58740618130100033626",
                "payer": "Testkonto Nummer 2",
            },
            {
                "amount": "1.00",
                "date": "2013-12-27",
                "reference": "R CKBUCHUNG",
                "external_id": "2013122711085260000",
                "payer": "Testkonto Nummer 2",
            },
            {
                "amount": "-6.00",
                "date": "2013-12-27",
                "reference": "STZV-PmInf27122013-11:02-2",
                "external_id": "2013122711513230000",
            },
        ]
        filename = "camt.053_sepatools.xml"
        self._test_from_sample_file(filename, expected_parsed)

    def test_sample_file_bundesbank(self):
        expected_parsed = [
            {
                "amount": "100000.00",
                "date": "2024-03-13",
                "reference": "",
                "external_id": "103600002791/0019200002",
            },
            {
                "amount": "-25000.00",
                "date": "2024-03-13",
                "reference": "",
                "external_id": "049000039704/0019000002",
            },
            {
                "amount": "-20000.00",
                "date": "2024-03-13",
                "reference": "",
                "external_id": "047200003598/0002000001",
                "iban": "DE98200000000020002633",
            },
            {
                "amount": "-15.00",
                "date": "2024-03-13",
                "reference": "",
                "external_id": "047200003598/0002000001",
            },
            {
                "amount": "145015.00",
                "date": "2024-03-13",
                "reference": "",
                "external_id": "051500000059/0019000003",
            },
            {
                "amount": "50000.00",
                "date": "2024-03-13",
                "reference": "VWZ pacs008 RTGS nach DOTA",
                "external_id": "105600004525/0019200003",
            },
            {
                "amount": "80000.00",
                "date": "2024-03-13",
                "reference": "VWZ pacs009 RTGS nach DOTA",
                "external_id": "051800000156/0019000004",
            },
            {
                "amount": "-30000.00",
                "date": "2024-03-13",
                "reference": "VWZ pacs009 DOTA nach MCA",
                "external_id": "055100000086/0019000005",
            },
            {
                "amount": "-120000.00",
                "date": "2024-03-13",
                "reference": "VWZ pacs009 DOTA nach RTGS",
                "external_id": "001400001221/0019000006",
            },
            {
                "amount": "100000.00",
                "date": "2024-03-13",
                "reference": "",
                "external_id": "016900004681/0002000002",
                "iban": "DE98200000000020002633",
            },
            {
                "amount": "-280000.00",
                "date": "2024-03-13",
                "reference": "VWZ pacs008 DOTA nach RTGS",
                "external_id": "010300005153/0019000007",
                "iban": "DE00IBANbeiTestbank",
            },
        ]

        filename = "camt.053_bundesbank.xml"
        self._test_from_sample_file(filename, expected_parsed)
