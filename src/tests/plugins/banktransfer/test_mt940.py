import io
import pprint

from pretix.plugins.banktransfer.mt940import import parse

TEST_DATA = [
    # Source: https://www.ksk-koeln.de/Produkte/girokonten/Elektronisches%20Bezahlen/datenstruktur-mt940-swift.pdfx
    """
:20:951110
:25:45050050/76198810
:28:27/01
:60F:C951016DEM84349,74
:61:951017D6800,NCHK16703074
:86:999PN5477SCHECK-NR. 0000016703074
:61:951017D620,3NSTON
:86:999PN0911DAUERAUFTR.NR. 14
:61:951017C18500,NCLRN
:86:999PN2406SCHECK
:61:951015D14220,NBOEN
:86:999PN0920WECHSEL
:61:951017D1507,NTRFN
:86:999PN0920SCHNELLUEB
:61:951024C4200,NMSCN
:86:999PN2506AUSSENH. NR. 1
:61:951017D19900,NTRFN
:86:999PN0907UEBERTRAG
:61:951017D400,NTRFN
:86:999PN0891BTX
:61:951018C3656,74NMSCN
:86:999PN0850EINZAHLG.N
:61:951019C23040,NMSCN
:86:999PN0812LT.ANLAGE
:61:951027D5862,14NCHKN
:86:999PN5329AUSLSCHECK
:62F:C951017DEM84437,04
""",
    # Source: https://www.bayernlb.de/internet/media/de/internet_4/de_1/downloads_5
    # /0800_financial_office_it_operations_5/4200_1/sepa_5/SEPAMT940_942.pdf
    # Slightly modified in the last row since there is no 31th of November...
    """
:20:1234567
:21:9876543210
:25:10020030/1234567
:28C:5/1
:60F:C021101EUR2187,95
:61:0211011102DR800,NSTONONREF//55555
:86:008?00DAUERAUFTRAG?100599?20Miete Novem
ber?3010020030?31234567
?32MUELLER?34339
:61:0211021102CR3000,NTRFNONREF//55555
:86:051?00UEBERWEISUNG?100599?20Gehalt Oktob
er
?21Firma Mustermann GmbH?3050060400?31084756
4700?32MUELLER?34339
:62F:C021130EUR4387,95
""",
    # http://wiki.nuclos.de/display/NW/7+MT940%3A+Beispiele
    """
:20:STARTUMSE
:25:10010010/1111111111
:28C:00001/001
:60F:C120131EUR8200,90
:61:1202020102DR400,62N033NONREF
:86:077?00Überweisung beleglos?109310?20RECHNUNGSNR. 1210815 ?21K
UNDENNR. 01234 ?22DATUM 01.02.2012?3020020020?2222222222?32MARTHA
MUELLER?34999
:61:1202030103DR1210,00N012NONREF
:86:008?00Dauerauftrag?107000?20MIETE GOETHESTR. 12?3030030030?31
3333333333?32ABC IMMOBILIEN GMBH?34997
:61:1202030103CR30,00N062NONREF
:86:051?00Überweisungseingang?109265?20RECHNUNG 20120188?21STEFAN
 SCHMIDT?23KUNDENR. 4711,?3040040040?4444444444?32STEFAN SCHMIDT
:61:1202030103CR89,97N060NONREF//000000000001
:86:052?00Überweisungseingang?109265?20RECHNUNG 20120165?21PETER
 PETERSEN?3050050050?315555555555?32PETER PETERSEN
:62F:C120203EUR6710,50
""",
    # http://www.national-bank.de/fileadmin/user_upload/nationalbank/Service_Center/Electronic_Banking_Center
    # /Downloads/Handbuecher_und_Bedingungen/swift_mt940.pdf
    """
:20:STARTUMS
:25:1222333444
:28:1/1
:NS:22Test GmbH
23Testkonto
240,800
25010102311202
3037010000
3190000022
:60F:C020315DEM0,00
:61:0203170320CM5000,00S05168790452
:NS:01Verwendungszweck 1
02Verwendungszweck 2
15Empfänger
17Buchungstext
1812345
191000
204711
:61:020322CM20000,00NCHG
:61:020322CM20000,00S051
:61:020322CM20000,00S051
:61:020322CM20000,00S051
:61:020322CM20000,00S051
:62M:C020315105000,00
:20:STARTUMS
:25:1222333444
:28:1/1
:NS:223037010000
:60M:C020315DEM105000,00
:61:020322CM20000,00S051
:61:020322CM20000,00S051
:62F:C020315145000,00
:20:STARTUMS
:25:3346780111
:28:2/1
:NS:22Meyer + Schneider
23Testkonto
3037010000
3187132101
:60F:C020324DEM145000,00
:61:020324DM50000,00S051
:NS:01bekannt
1812345
:62F:C02032495000,00
""",
    # From a customer (N26)
    """
:20:STARTUMS
:25:DE13495179316396679327
:28C:0
:60F:C170823EUR0,
:61:1708230823C12,NMSCNONREF
:86:000?32Peter Schneider?31DE13495179316396679327?30NOTABIC?20De
mocon-Abcde (Peter Schneider?21), Kategorie: Alles - E?22innahmen - V
eranstaltungen ?23Democon #1111
:61:1708230823C12,NMSCNONREF
:86:000?32Peter Schneider?31DE13495179316396679327?30NOTABIC?20De
mocon-Abcde (Peter Schneider?21), Kategorie: Alles - E?22innahmen - V
eranstaltungen ?23Democon #1111
:62F:C170823EUR24,
-
:20:STARTUMS
:25:DE13495179316396679327
:28C:0
:60F:C170824EUR24,
:61:1708240824C12,NMSCNONREF
:86:000?32Peter Schneider?31DE13495179316396679327?30NOTABIC?20De
mocon-Abcde (Peter Schneider?21), Kategorie: Alles- E?22innahmen - V
eranstaltungen ?23Democon #1111
:62F:C170824EUR36,
-
"""
]

EXPECTED = [
    [
        {'amount': '-6800.00',
         'date': '2095-10-17',
         'reference': '999PN5477SCHECK-NR. 0000016703074\n16703074'},
        {'amount': '-620.30',
         'date': '2095-10-17',
         'reference': '999PN0911DAUERAUFTR.NR. 14\nN'},
        {'amount': '18500.00',
         'date': '2095-10-17',
         'reference': '999PN2406SCHECK\nN'},
        {'amount': '-14220.00',
         'date': '2095-10-15',
         'reference': '999PN0920WECHSEL\nN'},
        {'amount': '-1507.00',
         'date': '2095-10-17',
         'reference': '999PN0920SCHNELLUEB\nN'},
        {'amount': '4200.00',
         'date': '2095-10-24',
         'reference': '999PN2506AUSSENH. NR. 1\nN'},
        {'amount': '-19900.00',
         'date': '2095-10-17',
         'reference': '999PN0907UEBERTRAG\nN'},
        {'amount': '-400.00',
         'date': '2095-10-17',
         'reference': '999PN0891BTX\nN'},
        {'amount': '3656.74',
         'date': '2095-10-18',
         'reference': '999PN0850EINZAHLG.N\nN'},
        {'amount': '23040.00',
         'date': '2095-10-19',
         'reference': '999PN0812LT.ANLAGE\nN'},
        {'amount': '-5862.14',
         'date': '2095-10-27',
         'reference': '999PN5329AUSLSCHECK\nN'}
    ],
    [
        {'amount': '-800.00',
         'date': '2002-11-01',
         'payer': 'MUELLER',
         'iban': '234567',
         'bic': '10020030',
         'reference': 'Miete November'},
        {'amount': '3000.00',
         'date': '2002-11-02',
         'payer': 'MUELLER',
         'iban': '0847564700',
         'bic': '50060400',
         'reference': 'Gehalt Oktober Firma Mustermann GmbH'},
    ],
    [
        {'amount': '-400.62',
         'date': '2012-02-02',
         'payer': 'MARTHAMUELLER',
         'bic': '20020020',
         'reference': 'RECHNUNGSNR. 1210815 KUNDENNR. 01234 22222222 DATUM 01.02.2012'},
        {'amount': '-1210.00',
         'date': '2012-02-03',
         'reference': 'MIETE GOETHESTR. 12',
         'payer': 'ABC IMMOBILIEN GMBH',
         'bic': '30030030',
         'iban': '3333333333'},
        {'amount': '30.00',
         'date': '2012-02-03',
         'payer': 'STEFAN SCHMIDT',
         'bic': '40040040',
         'reference': 'RECHNUNG 20120188 STEFAN SCHMIDTKUNDENR. 4711,'},
        {'amount': '89.97',
         'date': '2012-02-03',
         'payer': 'PETER PETERSEN',
         'iban': '5555555555',
         'bic': '50050050',
         'reference': 'RECHNUNG 20120165 PETER PETERSEN'}
    ],
    [
        {'amount': '5000.00', 'date': '2002-03-17', 'reference': '68790452'},
        {'amount': '20000.00', 'date': '2002-03-22', 'reference': ''},
        {'amount': '20000.00', 'date': '2002-03-22', 'reference': ''},
        {'amount': '20000.00', 'date': '2002-03-22', 'reference': ''},
        {'amount': '20000.00', 'date': '2002-03-22', 'reference': ''},
        {'amount': '20000.00', 'date': '2002-03-22', 'reference': ''},
        {'amount': '20000.00', 'date': '2002-03-22', 'reference': ''},
        {'amount': '20000.00', 'date': '2002-03-22', 'reference': ''},
        {'amount': '-50000.00', 'date': '2002-03-24', 'reference': ''}
    ],
    [
        {'amount': '12.00',
         'date': '2017-08-23',
         'payer': 'Peter Schneider',
         'iban': 'DE13495179316396679327',
         'bic': 'NOTABIC',
         'reference': 'Democon-Abcde (Peter Schneider ), Kategorie: Alles - E innahmen - Veranstaltungen Democon #1111'},
        {'amount': '12.00',
         'date': '2017-08-23',
         'payer': 'Peter Schneider',
         'iban': 'DE13495179316396679327',
         'bic': 'NOTABIC',
         'reference': 'Democon-Abcde (Peter Schneider ), Kategorie: Alles - E innahmen - Veranstaltungen Democon #1111'},
        {'amount': '12.00',
         'date': '2017-08-24',
         'payer': 'Peter Schneider',
         'iban': 'DE13495179316396679327',
         'bic': 'NOTABIC',
         'reference': 'Democon-Abcde (Peter Schneider ), Kategorie: Alles- E innahmen - Veranstaltungen Democon #1111'},
    ]
]


def test_parse():
    for i, d in enumerate(TEST_DATA):
        parsed = parse(io.BytesIO(d.encode('utf-8')))
        pp = pprint.PrettyPrinter(indent=4)
        pp.pprint(parsed)
        assert parsed == EXPECTED[i]
