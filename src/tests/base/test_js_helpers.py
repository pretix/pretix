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
import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import Event, Organizer


@pytest.mark.django_db
def test_no_invoice_address(client):
    response = client.get('/js_helpers/address_form/?country=DE')
    assert response.json() == {
        'city': {'required': 'if_any'},
        'data': [],
        'state': {'label': 'State', 'required': False, 'visible': False},
        'street': {'required': 'if_any'},
        'vat_id': {'helptext_visible': True, 'label': 'VAT ID', 'required': False, 'visible': True},
        'zipcode': {'required': 'if_any'}
    }

    response = client.get('/js_helpers/address_form/?country=CR')
    assert response.json() == {
        'city': {'required': False},
        'data': [],
        'state': {'label': 'State', 'required': False, 'visible': False},
        'street': {'required': 'if_any'},
        'vat_id': {'helptext_visible': True, 'label': 'VAT ID', 'required': False, 'visible': False},
        'zipcode': {'required': False}
    }

    response = client.get('/js_helpers/address_form/?country=US')
    d = response.json()
    assert d['state'] == {'label': 'State', 'required': 'if_any', 'visible': True}
    assert d['data'][0] == {'code': 'AL', 'name': 'Alabama'}

    response = client.get('/js_helpers/address_form/?country=IT')
    d = response.json()
    assert d['state'] == {'label': 'Province', 'required': 'if_any', 'visible': True}
    assert d['data'][0] == {'code': 'AG', 'name': 'Agrigento'}


@pytest.fixture
@scopes_disabled()
def event():
    o = Organizer.objects.create(name='Dummy', slug='org')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='ev',
        date_from=now(), plugins='tests.testdummy'
    )
    return event


@pytest.mark.django_db
def test_invalid_event(client):
    response = client.get(
        '/js_helpers/address_form/?country=DE&invoice=true&organizer=test&event=test'
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_provider_only_email_available(client, event):
    response = client.get(
        '/js_helpers/address_form/?country=DE&invoice=true&organizer=org&event=ev&transmission_type_required=true'
    )
    assert response.status_code == 200
    d = response.json()
    assert d == {
        'city': {'required': 'if_any'},
        'data': [],
        'state': {'label': 'State', 'required': False, 'visible': False},
        'street': {'required': 'if_any'},
        'transmission_email_address': {'required': False, 'visible': False},
        'transmission_email_other': {'required': False, 'visible': False},
        'transmission_it_sdi_codice_fiscale': {'required': False, 'visible': False},
        'transmission_it_sdi_pec': {'required': False, 'visible': False},
        'transmission_it_sdi_recipient_code': {'required': False, 'visible': False},
        'transmission_peppol_participant_id': {'required': False, 'visible': False},
        'transmission_type': {'visible': False},
        'transmission_types': [{'code': 'email', 'name': 'Email'}],
        'vat_id': {'helptext_visible': True, 'label': 'VAT ID', 'required': False, 'visible': True},
        'zipcode': {'required': 'if_any'}
    }


@pytest.mark.django_db
def test_provider_italy_sdi_not_enforced_when_optional(client, event):
    response = client.get(
        '/js_helpers/address_form/?country=IT&invoice=true&organizer=org&event=ev&transmission_type_required=false'
    )
    assert response.status_code == 200
    d = response.json()
    del d['data']
    assert d == {
        'city': {'required': 'if_any'},
        'state': {'label': 'Province', 'required': 'if_any', 'visible': True},
        'street': {'required': 'if_any'},
        'transmission_email_address': {'required': False, 'visible': False},
        'transmission_email_other': {'required': False, 'visible': False},
        'transmission_it_sdi_codice_fiscale': {'required': False, 'visible': False},
        'transmission_it_sdi_pec': {'required': False, 'visible': False},
        'transmission_it_sdi_recipient_code': {'required': False, 'visible': False},
        'transmission_peppol_participant_id': {'required': False, 'visible': False},
        'transmission_type': {'visible': True},
        'transmission_types': [{'code': 'it_sdi', 'name': 'Exchange System (SdI)'}],
        'vat_id': {'helptext_visible': True, 'label': 'VAT ID / P.IVA', 'required': False, 'visible': True},
        'zipcode': {'required': 'if_any'}
    }


@pytest.mark.django_db
def test_provider_italy_sdi_enforced_individual(client, event):
    response = client.get(
        '/js_helpers/address_form/?country=IT&invoice=true&organizer=org&event=ev&transmission_type_required=true'
    )
    assert response.status_code == 200
    d = response.json()
    del d['data']
    assert d == {
        'city': {'required': True},
        'state': {'label': 'Province', 'required': True, 'visible': True},
        'street': {'required': True},
        'transmission_email_address': {'required': False, 'visible': False},
        'transmission_email_other': {'required': False, 'visible': False},
        'transmission_it_sdi_codice_fiscale': {'required': True, 'visible': True},
        'transmission_it_sdi_pec': {'required': False, 'visible': True},
        'transmission_it_sdi_recipient_code': {'required': False, 'visible': False},
        'transmission_peppol_participant_id': {'required': False, 'visible': False},
        'transmission_type': {'visible': True},
        'transmission_types': [{'code': 'it_sdi', 'name': 'Exchange System (SdI)'}],
        'vat_id': {'helptext_visible': True, 'label': 'VAT ID / P.IVA', 'required': False, 'visible': True},
        'zipcode': {'required': True}
    }


@pytest.mark.django_db
def test_provider_italy_sdi_enforced_business(client, event):
    response = client.get(
        '/js_helpers/address_form/?country=IT&invoice=true&organizer=org&event=ev&transmission_type_required=true'
        '&is_business=business'
    )
    assert response.status_code == 200
    d = response.json()
    del d['data']
    assert d == {
        'city': {'required': True},
        'state': {'label': 'Province', 'required': True, 'visible': True},
        'street': {'required': True},
        'transmission_email_address': {'required': False, 'visible': False},
        'transmission_email_other': {'required': False, 'visible': False},
        'transmission_it_sdi_codice_fiscale': {'required': False, 'visible': True},
        'transmission_it_sdi_pec': {'required': True, 'visible': True},
        'transmission_it_sdi_recipient_code': {'required': True, 'visible': True},
        'transmission_peppol_participant_id': {'required': False, 'visible': False},
        'transmission_type': {'visible': True},
        'transmission_types': [{'code': 'it_sdi', 'name': 'Exchange System (SdI)'}],
        'vat_id': {'helptext_visible': False, 'label': 'VAT ID / P.IVA', 'required': True, 'visible': True},
        'zipcode': {'required': True}
    }


@pytest.mark.django_db
def test_vat_id_enforced(client, event):
    response = client.get(
        '/js_helpers/address_form/?country=GR&invoice=true&organizer=org&event=ev'
        '&is_business=business'
    )
    assert response.status_code == 200
    d = response.json()
    del d['data']
    assert d == {
        'city': {'required': 'if_any'},
        'state': {'label': 'State', 'required': False, 'visible': False},
        'street': {'required': 'if_any'},
        'transmission_email_address': {'required': False, 'visible': False},
        'transmission_email_other': {'required': False, 'visible': False},
        'transmission_it_sdi_codice_fiscale': {'required': False, 'visible': False},
        'transmission_it_sdi_pec': {'required': False, 'visible': False},
        'transmission_it_sdi_recipient_code': {'required': False, 'visible': False},
        'transmission_peppol_participant_id': {'required': False, 'visible': False},
        'transmission_type': {'visible': True},
        'transmission_types': [{'code': 'email', 'name': 'Email'}, {'code': 'peppol', 'name': 'Peppol'}],
        'vat_id': {'helptext_visible': False, 'label': 'VAT ID / TIN', 'required': True, 'visible': True},
        'zipcode': {'required': 'if_any'}
    }


@pytest.mark.django_db
def test_email_peppol_choice(client, event):
    response = client.get(
        '/js_helpers/address_form/?country=DE&invoice=true&organizer=org&event=ev'
        '&is_business=business&transmission_type_required=true'
    )
    assert response.status_code == 200
    d = response.json()
    assert d == {
        'city': {'required': 'if_any'},
        'data': [],
        'state': {'label': 'State', 'required': False, 'visible': False},
        'street': {'required': 'if_any'},
        'transmission_email_address': {'required': False, 'visible': True},
        'transmission_email_other': {'required': False, 'visible': True},
        'transmission_it_sdi_codice_fiscale': {'required': False, 'visible': False},
        'transmission_it_sdi_pec': {'required': False, 'visible': False},
        'transmission_it_sdi_recipient_code': {'required': False, 'visible': False},
        'transmission_peppol_participant_id': {'required': False, 'visible': False},
        'transmission_type': {'visible': True},
        'transmission_types': [
            {'code': 'email', 'name': 'Email'},
            {'code': 'peppol', 'name': 'Peppol'},
        ],
        'vat_id': {'helptext_visible': True, 'label': 'VAT ID', 'required': False, 'visible': True},
        'zipcode': {'required': 'if_any'}
    }

    response = client.get(
        '/js_helpers/address_form/?country=DE&invoice=true&organizer=org&event=ev'
        '&is_business=business&transmission_type=peppol'
    )
    assert response.status_code == 200
    d = response.json()
    assert d == {
        'city': {'required': True},
        'data': [],
        'state': {'label': 'State', 'required': False, 'visible': False},
        'street': {'required': True},
        'transmission_email_address': {'required': False, 'visible': False},
        'transmission_email_other': {'required': False, 'visible': False},
        'transmission_it_sdi_codice_fiscale': {'required': False, 'visible': False},
        'transmission_it_sdi_pec': {'required': False, 'visible': False},
        'transmission_it_sdi_recipient_code': {'required': False, 'visible': False},
        'transmission_peppol_participant_id': {'required': True, 'visible': True},
        'transmission_type': {'visible': True},
        'transmission_types': [
            {'code': 'email', 'name': 'Email'},
            {'code': 'peppol', 'name': 'Peppol'},
        ],
        'vat_id': {'helptext_visible': True, 'label': 'VAT ID', 'required': False, 'visible': True},
        'zipcode': {'required': True}
    }
