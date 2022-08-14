import pytest
import responses
from requests import Timeout

from pretix.base.services.tax import VATIDTemporaryError, validate_vat_id, VATIDFinalError


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
