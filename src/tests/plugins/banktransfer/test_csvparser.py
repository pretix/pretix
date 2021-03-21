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
import os.path

from django.test import TestCase

# Do NOT use relative imports here
from pretix.plugins.banktransfer import csvimport

# These tests need data files. Don't worry, they are fully anonymized,
# all IBANs are random/fake.
DATA_DIR = os.path.dirname(__file__)


class CsvImportTest(TestCase):
    def _test_from_sample_file(self, filename, expected, hint, expected_parsed):
        with open(os.path.join(DATA_DIR, filename), 'rb') as f:
            data = csvimport.get_rows_from_file(f)
            self.assertEqual(data, expected)
            parsed, good = csvimport.parse(data, hint)
            self.assertEqual(parsed, expected_parsed)

    def test_sample_file_bbbank(self):
        expected = [
            ['Buchungstag', 'Valuta', 'Auftraggeber/Zahlungsempfänger', 'Empfänger/Zahlungspflichtiger',
             'Konto-Nr.', 'BLZ', 'Vorgang/Verwendungszweck', 'Währung', 'Umsatz', ' '],
            ['10.04.2015', '10.04.2015', 'Mustermann, Max', 'Einzug ', '', '',
             'LASTSCHRIFT\nEinzug Nutzungsgebuehren IB\nAN: DE76574670095813552253',
             'EUR', '42,23', 'S'],
            ['08.04.2015', '08.04.2015', 'Mustermann, Max', 'Kunde, Karl', '', '',
             'GUTSCHRIFT\nTicket 2015XAZTY IBAN: DE83\n839857672994615084', 'EUR', '42,23', 'H'],
            [],
            ['07.04.2015', '', '', '', '', '', 'EUR', 'Anfangssaldo', '1.337,00', 'H'],
            ['10.04.2015', '', '', '', '', '', 'EUR', 'Endsaldo', '1.337,00', 'H']
        ]
        hint = {
            'payer': [3],
            'reference': [6],
            'date': 1,
            'amount': 8,
            'cols': 10,
        }
        expected_parsed = [
            {'date': '10.04.2015', 'reference': 'LASTSCHRIFT\nEinzug Nutzungsgebuehren IB\nAN: DE76574670095813552253',
             'payer': 'Einzug', 'amount': '42,23'},
            {'date': '08.04.2015', 'reference': 'GUTSCHRIFT\nTicket 2015XAZTY IBAN: DE83\n839857672994615084',
             'payer': 'Kunde, Karl', 'amount': '42,23'},
        ]
        filename = 'csvimport_data_de_bbbank.csv'
        self._test_from_sample_file(filename, expected, hint, expected_parsed)

    def test_sample_file_sparkasse(self):
        expected = [
            ['Auftragskonto', 'Buchungstag', 'Valutadatum', 'Buchungstext', 'Verwendungszweck',
             'Begünstigter/Zahlungspflichtiger', 'Kontonummer', 'BLZ', 'Betrag', 'Währung', 'Info'],
            ['123456', '09.03', '09.03.15', 'ONLINE-UEBERWEISUNG', 'SVWZ+Begleichung Rechnung 1234',
             'Max Mustermann', 'DE13495179316396679327', 'THISISNOBIC', '-23,42', 'EUR', 'Umsatz gebucht'],
            ['123456', '03.03', '03.03.15', 'GUTSCHRIFT', 'EREF+123456789 Ticket-Bestellung 2015XALSK', 'Karl Kunde',
             'DE89701226010601035858', 'THISISNOBIC', '42,32', 'EUR', 'Umsatz gebucht']
        ]
        hint = {
            'payer': [5, 6, 7],
            'reference': [4],
            'date': 2,
            'amount': 8,
            'cols': 11,
        }
        expected_parsed = [
            {'date': '09.03.15', 'reference': 'SVWZ+Begleichung Rechnung 1234',
             'payer': 'Max Mustermann\nDE13495179316396679327\nTHISISNOBIC', 'amount': '-23,42'},
            {'date': '03.03.15', 'reference': 'EREF+123456789 Ticket-Bestellung 2015XALSK',
             'payer': 'Karl Kunde\nDE89701226010601035858\nTHISISNOBIC', 'amount': '42,32'}
        ]
        filename = 'csvimport_data_de_sparkassernn.csv'
        self._test_from_sample_file(filename, expected, hint, expected_parsed)

    def test_sample_file_gls(self):
        expected = [
            ['Kontonummer', 'Buchungstag', 'Wertstellung', 'Auftraggeber/Empfänger', 'Buchungstext', 'VWZ1', 'VWZ2',
             'VWZ3', 'VWZ4', 'VWZ5', 'VWZ6', 'VWZ7', 'VWZ8', 'VWZ9', 'VWZ10', 'VWZ11', 'VWZ12', 'VWZ13', 'VWZ14',
             'Betrag', 'Kontostand', 'Währung'],
            ['123456789', '09.04.2015', '09.04.2015', 'Lars Lieferant', 'OnlBanking-Euro-Überweisung',
             'BIC:THISINOBIC', 'IBAN:DE59433524647958971194', 'Datum: 09.04.15 Zeit: 10:47', 'KD 1234567 TAN 123456',
             'Rechnung Nr. 123', '456', '', '', '', '', '', '', '', '', '-42,00', '1.337,00', 'EUR'],
            ['123456789', '08.04.2015', '08.04.2015', 'Karl Kunde', 'SEPA-Überweisung', 'Ticket-Bestellung',
             'Bestellnummer 2015ABC', 'DEV', '', '', '', '', '', '', '', '', '', '', '', '12,00', '1.325,00', 'EUR']
        ]
        hint = {
            'payer': [3],
            'reference': [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
            'date': 2,
            'amount': 19,
            'cols': 22,
        }
        expected_parsed = [
            {'date': '09.04.2015',
             'reference': 'BIC:THISINOBIC\nIBAN:DE59433524647958971194\nDatum: 09.04.15 Zeit: 10:47\nKD 1234567 TAN '
                          '123456\nRechnung Nr. 123\n456',
             'amount': '-42,00', 'payer': 'Lars Lieferant'},
            {'date': '08.04.2015', 'reference': 'Ticket-Bestellung\nBestellnummer 2015ABC\nDEV',
             'amount': '12,00', 'payer': 'Karl Kunde'}
        ]
        filename = "csvimport_data_de_gls.csv"
        self._test_from_sample_file(filename, expected, hint, expected_parsed)

    def test_sample_file_dab(self):
        expected = [
            ['Buchungstag', 'Valuta', 'Buchungstext', 'Auftraggeber / Empfänger', 'Verwendungszweck', 'Betrag in EUR',
             ''],
            ['09.04.2015', '09.04.2015', 'SEPA-Überweisung', 'Karl Kunde', 'Bestellung 2015ABCDE', '23,00', ''],
            ['09.04.2015', '09.04.2015', 'SEPA-Überweisung', 'Karla Kundin', 'Bestellung 2015FGHIJ', '42,00', '']
        ]
        hint = {
            'payer': [3],
            'reference': [4],
            'date': 1,
            'amount': 5,
            'cols': 7,
        }
        expected_parsed = [
            {'payer': 'Karl Kunde', 'reference': 'Bestellung 2015ABCDE', 'amount': '23,00', 'date': '09.04.2015'},
            {'payer': 'Karla Kundin', 'reference': 'Bestellung 2015FGHIJ', 'amount': '42,00', 'date': '09.04.2015'}
        ]
        filename = "csvimport_data_de_dab.csv"
        self._test_from_sample_file(filename, expected, hint, expected_parsed)

    def test_sample_file_postbank(self):
        expected = [
            ['Buchungstag', 'Wertstellung', 'Umsatzart', 'Buchungsdetails', 'Auftraggeber', 'Empfänger',
             'Betrag (€)', 'Saldo (€)'],
            ['07.08.2016', '01.08.2016', 'Gutschrift', 'Verwendungszweck 2015ABCDE', 'Karla Kundin',
             'Fiktive Veranstaltungsgesellschaft mbH', '\xA4 42,00', '\xA4 1.337,42'],
            ['29.07.2016', '29.07.2016', 'Gutschrift', 'Referenz NOTPROVIDED', 'Lars Lieferant',
             'Fiktive Veranstaltungsgesellschaft mbH', '\xA4 56,76', '\xA4 1.337,42'],
        ]
        hint = {
            'payer': [4],
            'reference': [3],
            'date': 0,
            'amount': 6,
            'cols': 8,
        }
        expected_parsed = [
            {'payer': 'Karla Kundin', 'reference': 'Verwendungszweck 2015ABCDE', 'amount': '42,00',
             'date': '07.08.2016'},
            {'payer': 'Lars Lieferant', 'reference': 'Referenz NOTPROVIDED', 'amount': '56,76', 'date': '29.07.2016'}
        ]
        filename = "csvimport_data_de_postbank.csv"
        self._test_from_sample_file(filename, expected, hint, expected_parsed)
