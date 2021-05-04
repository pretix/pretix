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
from django_scopes import scopes_disabled
from i18nfield.strings import LazyI18nString


@pytest.fixture
def membershiptype(organizer, event):
    return organizer.membership_types.create(
        name=LazyI18nString({"en": "Week pass"}),
        transferable=True,
        allow_parallel_usage=False,
        max_usages=15,
    )


TEST_TYPE_RES = {
    "name": {
        "en": "Week pass"
    },
    "transferable": True,
    "allow_parallel_usage": False,
    "max_usages": 15,
}


@pytest.mark.django_db
def test_membershiptype_list(token_client, organizer, membershiptype):
    res = dict(TEST_TYPE_RES)
    res["id"] = membershiptype.pk

    resp = token_client.get('/api/v1/organizers/{}/membershiptypes/'.format(organizer.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']


@pytest.mark.django_db
def test_membershiptype_detail(token_client, organizer, membershiptype):
    res = dict(TEST_TYPE_RES)
    res["id"] = membershiptype.pk
    resp = token_client.get('/api/v1/organizers/{}/membershiptypes/{}/'.format(organizer.slug, membershiptype.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_membershiptype_create(token_client, organizer):
    resp = token_client.post(
        '/api/v1/organizers/{}/membershiptypes/'.format(organizer.slug),
        format='json',
        data={
            "name": {
                "en": "Week pass"
            },
            "transferable": True,
            "allow_parallel_usage": False,
            "max_usages": 15,
        }
    )
    assert resp.status_code == 201
    with scopes_disabled():
        membershiptype = organizer.membership_types.get(id=resp.data['id'])
        assert str(membershiptype.name) == "Week pass"
        assert membershiptype.transferable
        assert not membershiptype.allow_parallel_usage


@pytest.mark.django_db
def test_membershiptype_patch(token_client, organizer, membershiptype):
    resp = token_client.patch(
        '/api/v1/organizers/{}/membershiptypes/{}/'.format(organizer.slug, membershiptype.pk),
        format='json',
        data={
            'transferable': False,
        }
    )
    assert resp.status_code == 200
    membershiptype.refresh_from_db()
    assert not membershiptype.transferable


@pytest.mark.django_db
def test_membershiptype_delete(token_client, organizer, membershiptype):
    resp = token_client.delete(
        '/api/v1/organizers/{}/membershiptypes/{}/'.format(organizer.slug, membershiptype.pk),
    )
    assert resp.status_code == 204
    assert not organizer.membership_types.exists()
