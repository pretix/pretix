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
import pytest
import responses
from requests import Timeout

from pretix.base.services.tax import (
    VATIDFinalError, VATIDTemporaryError, validate_vat_id,
)


def test_unknown_country():
    with pytest.raises(VATIDTemporaryError):
        validate_vat_id('TR12345', 'TR')


@responses.activate
def test_eu_invalid_format():
    with pytest.raises(VATIDFinalError):
        validate_vat_id('AT12345', 'AT')


@responses.activate
def test_eu_no_prefix():
    with pytest.raises(VATIDFinalError):
        validate_vat_id('12345', 'AT')


@responses.activate
def test_eu_country_mismatch():
    with pytest.raises(VATIDFinalError):
        validate_vat_id('AT12345', 'DE')


@responses.activate
def test_eu_server_down():
    def _callback(request):
        raise Timeout

    responses.add_callback(
        responses.POST,
        'https://ec.europa.eu/taxation_customs/vies/services/checkVatService',
        callback=_callback
    )

    with pytest.raises(VATIDTemporaryError):
        validate_vat_id('ATU36801500', 'AT')


@responses.activate
def test_eu_server_error():
    responses.add(
        responses.POST,
        'https://ec.europa.eu/taxation_customs/vies/services/checkVatService',
        body='error',
        status=500
    )

    with pytest.raises(VATIDTemporaryError):
        validate_vat_id('ATU36801500', 'AT')


@responses.activate
def test_eu_id_invalid():
    responses.add(
        responses.POST,
        'https://ec.europa.eu/taxation_customs/vies/services/checkVatService',
        body="""<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
            <soap:Body>
                <checkVatResponse xmlns="urn:ec.europa.eu:taxud:vies:services:checkVat:types">
                    <countryCode>AT</countryCode>
                    <vatNumber>U36801500</vatNumber>
                    <requestDate>2014-12-17+01:00</requestDate>
                    <valid>false</valid>
                    <name>STADT WIEN</name>
                    <address>UNKNOWN</address>
               </checkVatResponse>
            </soap:Body>
        </soap:Envelope>""",
        status=200
    )

    with pytest.raises(VATIDFinalError):
        validate_vat_id('ATU36801500', 'AT')


@responses.activate
def test_eu_id_valid():
    responses.add(
        responses.POST,
        'https://ec.europa.eu/taxation_customs/vies/services/checkVatService',
        body="""<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
            <soap:Body>
                <checkVatResponse xmlns="urn:ec.europa.eu:taxud:vies:services:checkVat:types">
                    <countryCode>AT</countryCode>
                    <vatNumber>U36801500</vatNumber>
                    <requestDate>2014-12-17+01:00</requestDate>
                    <valid>true</valid>
                    <name>STADT WIEN</name>
                    <address>UNKNOWN</address>
               </checkVatResponse>
            </soap:Body>
        </soap:Envelope>""",
        status=200
    )

    assert validate_vat_id('ATU36801500', 'AT') == 'ATU36801500'


@responses.activate
def test_NO_invalid_format():
    with pytest.raises(VATIDFinalError):
        validate_vat_id('NO12345', 'NO')


@responses.activate
def test_NO_server_down():
    def _callback(request):
        raise Timeout

    responses.add_callback(
        responses.GET,
        'https://data.brreg.no/enhetsregisteret/api/enheter/974760673',
        callback=_callback
    )

    with pytest.raises(VATIDTemporaryError):
        validate_vat_id('NO974760673 MVA', 'NO')


@responses.activate
def test_NO_server_error():
    responses.add(
        responses.GET,
        'https://data.brreg.no/enhetsregisteret/api/enheter/974760673',
        body='error',
        status=500
    )

    with pytest.raises(VATIDTemporaryError):
        validate_vat_id('NO974760673 MVA', 'NO')


@responses.activate
def test_NO_id_invalid():
    responses.add(
        responses.GET,
        'https://data.brreg.no/enhetsregisteret/api/enheter/974760673',
        body="",
        status=404
    )

    with pytest.raises(VATIDFinalError):
        validate_vat_id('NO974760673 MVA', 'NO')


@responses.activate
def test_NO_id_valid():
    responses.add(
        responses.GET,
        'https://data.brreg.no/enhetsregisteret/api/enheter/974760673',
        body='{"organisasjonsnummer":"974760673","navn":"REGISTERENHETEN I BRØNNØYSUND","organisasjonsform":{"kode":'
             '"ORGL","beskrivelse":"Organisasjonsledd","_links":{"self":{"href":"https://data.brreg.no/enhetsregisteret/api/'
             'organisasjonsformer/ORGL"}}},"hjemmeside":"www.brreg.no","postadresse":{"land":"Norge","landkode":"NO","postn'
             'ummer":"8910","poststed":"BRØNNØYSUND","adresse":["Postboks 900"],"kommune":"BRØNNØY","kommunenummer":"1813"}'
             ',"registreringsdatoEnhetsregisteret":"1995-08-09","registrertIMvaregisteret":false,"naeringskode1":{"beskrivels'
             'e":"Generell offentlig administrasjon","kode":"84.110"},"antallAnsatte":455,"overordnetEnhet":"912660680","for'
             'retningsadresse":{"land":"Norge","landkode":"NO","postnummer":"8900","poststed":"BRØNNØYSUND","adresse":["Havn'
             'egata 48"],"kommune":"BRØNNØY","kommunenummer":"1813"},"institusjonellSektorkode":{"kode":"6100","beskrivelse'
             '":"Statsforvaltningen"},"registrertIForetaksregisteret":false,"registrertIStiftelsesregisteret":false,"registr'
             'ertIFrivillighetsregisteret":false,"konkurs":false,"underAvvikling":false,"underTvangsavviklingEllerTvangsopp'
             'losning":false,"maalform":"Bokmål","_links":{"self":{"href":"https://data.brreg.no/enhetsregisteret/api/enheter'
             '/974760673"},"overordnetEnhet":{"href":"https://data.brreg.no/enhetsregisteret/api/enheter/912660680"}}}',
        status=200
    )

    assert validate_vat_id('NO974760673 MVA', 'NO') == 'NO974760673MVA'

# No tests for CH currently since it's harder to mock Zeep
