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
from django.core.exceptions import ValidationError
from responses import matchers

from pretix.base.customersso.oidc import (
    oidc_authorize_url, oidc_validate_and_complete_config,
    oidc_validate_authorization,
)
from pretix.base.models import Organizer
from pretix.base.models.customers import CustomerSSOProvider


def test_missing_parameter():
    config = {
        "base_url": "https://example.com",
        "client_id": "abc123",
        "client_secret": "abcdefghi",
        "uid_field": "sub",
    }
    with pytest.raises(ValidationError) as e:
        oidc_validate_and_complete_config(config)
    assert '"email_field" is missing' in str(e.value)


@responses.activate
def test_autoconf_unreachable():
    config = {
        "base_url": "https://example.com/provider",
        "client_id": "abc123",
        "client_secret": "abcdefghi",
        "uid_field": "sub",
        "email_field": "email",
        "scope": "foo bar",
    }
    responses.add(
        responses.GET,
        "https://example.com/provider/.well-known/openid-configuration",
        json={"error": "not found"},
        status=404
    )
    with pytest.raises(ValidationError) as e:
        oidc_validate_and_complete_config(config)
    assert "Unable to retrieve" in str(e.value)
    assert "404" in str(e.value)


@responses.activate
def test_incompatible():
    config = {
        "base_url": "https://example.com/provider",
        "client_id": "abc123",
        "client_secret": "abcdefghi",
        "uid_field": "sub",
        "email_field": "email",
        "scope": "foo bar",
    }

    responses.add(
        responses.GET,
        "https://example.com/provider/.well-known/openid-configuration",
        json={},
    )
    with pytest.raises(ValidationError) as e:
        oidc_validate_and_complete_config(config)
    assert "authorization_endpoint not set" in str(e.value)

    responses.reset()
    responses.add(
        responses.GET,
        "https://example.com/provider/.well-known/openid-configuration",
        json={
            "authorization_endpoint": "https://example.com/authorize",
        },
    )
    with pytest.raises(ValidationError) as e:
        oidc_validate_and_complete_config(config)
    assert "userinfo_endpoint not set" in str(e.value)

    responses.reset()
    responses.add(
        responses.GET,
        "https://example.com/provider/.well-known/openid-configuration",
        json={
            "authorization_endpoint": "https://example.com/authorize",
            "userinfo_endpoint": "https://example.com/userinfo",
        },
    )
    with pytest.raises(ValidationError) as e:
        oidc_validate_and_complete_config(config)
    assert "token_endpoint not set" in str(e.value)

    responses.reset()
    responses.add(
        responses.GET,
        "https://example.com/provider/.well-known/openid-configuration",
        json={
            "authorization_endpoint": "https://example.com/authorize",
            "token_endpoint": "https://example.com/token",
            "userinfo_endpoint": "https://example.com/userinfo",
        },
    )
    with pytest.raises(ValidationError) as e:
        oidc_validate_and_complete_config(config)
    assert "provider supports response types" in str(e.value)

    responses.reset()
    responses.add(
        responses.GET,
        "https://example.com/provider/.well-known/openid-configuration",
        json={
            "authorization_endpoint": "https://example.com/authorize",
            "token_endpoint": "https://example.com/token",
            "userinfo_endpoint": "https://example.com/userinfo",
            "response_types_supported": ["code"],
            "response_modes_supported": ["bogus"],
        },
    )
    with pytest.raises(ValidationError) as e:
        oidc_validate_and_complete_config(config)
    assert "provider supports response modes" in str(e.value)

    responses.reset()
    responses.add(
        responses.GET,
        "https://example.com/provider/.well-known/openid-configuration",
        json={
            "authorization_endpoint": "https://example.com/authorize",
            "token_endpoint": "https://example.com/token",
            "userinfo_endpoint": "https://example.com/userinfo",
            "response_types_supported": ["code"],
            "response_modes_supported": ["query"],
            "grant_types_supported": ["test"],
        },
    )
    with pytest.raises(ValidationError) as e:
        oidc_validate_and_complete_config(config)
    assert "provider supports grant types" in str(e.value)

    responses.reset()
    responses.add(
        responses.GET,
        "https://example.com/provider/.well-known/openid-configuration",
        json={
            "authorization_endpoint": "https://example.com/authorize",
            "token_endpoint": "https://example.com/token",
            "userinfo_endpoint": "https://example.com/userinfo",
            "response_types_supported": ["code"],
            "response_modes_supported": ["query"],
            "grant_types_supported": ["authorization_code"],
        },
    )
    with pytest.raises(ValidationError) as e:
        oidc_validate_and_complete_config(config)
    assert "not requesting" in str(e.value)

    config["scope"] = "openid foo"

    with pytest.raises(ValidationError) as e:
        oidc_validate_and_complete_config(config)
    assert "requesting scope" in str(e.value)


@responses.activate
def test_compatible():
    config = {
        "base_url": "https://example.com/provider",
        "client_id": "abc123",
        "client_secret": "abcdefghi",
        "uid_field": "sub",
        "email_field": "email",
        "scope": "openid email profile",
    }
    responses.add(
        responses.GET,
        "https://example.com/provider/.well-known/openid-configuration",
        json={
            "authorization_endpoint": "https://example.com/authorize",
            "token_endpoint": "https://example.com/token",
            "userinfo_endpoint": "https://example.com/userinfo",
            "response_types_supported": ["code"],
            "response_modes_supported": ["query"],
            "grant_types_supported": ["authorization_code"],
            "scopes_supported": ["openid", "email", "profile"],
            "claims_supported": ["email", "sub"]
        },
    )
    config = oidc_validate_and_complete_config(config)
    assert config["provider_config"]["token_endpoint"] == "https://example.com/token"


@pytest.fixture
def organizer():
    return Organizer.objects.create(name="Dummy", slug="dummy")


@pytest.fixture
def provider(organizer):
    return CustomerSSOProvider.objects.create(
        organizer=organizer,
        method="oidc",
        name="OIDC OP",
        configuration={
            "base_url": "https://example.com/provider",
            "client_id": "abc123",
            "client_secret": "abcdefghi",
            "uid_field": "sub",
            "email_field": "email",
            "scope": "openid email profile",
            "provider_config": {
                "authorization_endpoint": "https://example.com/authorize",
                "token_endpoint": "https://example.com/token",
                "userinfo_endpoint": "https://example.com/userinfo",
                "response_types_supported": ["code"],
                "response_modes_supported": ["query"],
                "grant_types_supported": ["authorization_code"],
                "scopes_supported": ["openid", "email", "profile"],
                "claims_supported": ["email", "sub"]
            }
        }
    )


@pytest.mark.django_db
def test_authorize_url(provider):
    assert (
        "https://example.com/authorize?"
        "response_type=code&"
        "client_id=abc123&"
        "scope=openid+email+profile&"
        "state=state_val&"
        "redirect_uri=https%3A%2F%2Fredirect%3Ffoo%3Dbar"
    ) == oidc_authorize_url(provider, "state_val", "https://redirect?foo=bar")


@pytest.mark.django_db
@responses.activate
def test_validate_authorization_invalid(provider):
    responses.add(
        responses.POST,
        "https://example.com/token",
        json={},
        status=400,
    )
    with pytest.raises(ValidationError):
        oidc_validate_authorization(provider, "code_received", "https://redirect?foo=bar")


@pytest.mark.django_db
@responses.activate
def test_validate_authorization_userinfo_invalid(provider):
    responses.add(
        responses.POST,
        "https://example.com/token",
        json={
            'access_token': 'test_access_token',
        },
        match=[
            matchers.urlencoded_params_matcher({
                "grant_type": "authorization_code",
                "code": "code_received",
                "redirect_uri": "https://redirect?foo=bar",
            })
        ],
    )
    responses.add(
        responses.GET,
        "https://example.com/userinfo",
        json={
            'uid': 'abcdf',
            'email': 'test@example.org'
        },
        match=[
            matchers.header_matcher({"Authorization": "Bearer test_access_token"})
        ],
    )
    with pytest.raises(ValidationError) as e:
        oidc_validate_authorization(provider, "code_received", "https://redirect?foo=bar")
    assert 'could not fetch' in str(e.value)


@pytest.mark.django_db
@responses.activate
def test_validate_authorization_valid(provider):
    responses.add(
        responses.POST,
        "https://example.com/token",
        json={
            'access_token': 'test_access_token',
        },
        match=[
            matchers.urlencoded_params_matcher({
                "grant_type": "authorization_code",
                "code": "code_received",
                "redirect_uri": "https://redirect?foo=bar",
            })
        ],
    )
    responses.add(
        responses.GET,
        "https://example.com/userinfo",
        json={
            'sub': 'abcdf',
            'email': 'test@example.org'
        },
        match=[
            matchers.header_matcher({"Authorization": "Bearer test_access_token"})
        ],
    )
    oidc_validate_authorization(provider, "code_received", "https://redirect?foo=bar")
