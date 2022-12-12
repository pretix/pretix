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
from django.core.exceptions import ValidationError

from pretix.base.addressvalidation import validate_address


@pytest.mark.parametrize(
    "input,output,all_optional",
    [
        # No address is allowed
        ({"name": "Peter"}, {"name": "Peter"}, False),
        # Country must be given if any part of the address is filled
        ({"street": "Main Street"}, {"country": ["This field is required."]}, False),
        # Country without any semantic validation
        (
            {"street": "Main Street", "country": "CR"},
            {"street": "Main Street", "country": "CR"},
            False,
        ),
        # Country that requires all fields except state to be filled
        (
            {"street": "Main Street", "country": "DE"},
            {"zipcode": ["This field is required."]},
            False,
        ),
        (
            {"street": "Main Street", "country": "DE", "zipcode": "12345"},
            {"city": ["This field is required."]},
            False,
        ),
        (
            {"city": "Heidelberg", "country": "DE", "zipcode": "12345"},
            {"street": ["This field is required."]},
            False,
        ),
        # All-optional flag works
        (
            {"street": "Main Street", "country": "DE"},
            {"street": "Main Street", "country": "DE"},
            True,
        ),
        (
            {"street": "Main Street", "country": "DE", "zipcode": "12345"},
            {"street": "Main Street", "country": "DE", "zipcode": "12345"},
            True,
        ),
        (
            {"city": "Heidelberg", "country": "DE", "zipcode": "12345"},
            {"city": "Heidelberg", "country": "DE", "zipcode": "12345"},
            True,
        ),
        (
            {
                "street": "Main Street",
                "city": "Heidelberg",
                "country": "DE",
                "zipcode": "12345",
            },
            True,
            False,
        ),
        # Country that requires state to be filled
        (
            {
                "street": "Main street",
                "city": "Heidelberg",
                "country": "US",
                "zipcode": "12345",
            },
            {"state": ["This field is required."]},
            False,
        ),
        # Country with zip code validation inherited from django-localflavor
        (
            {
                "street": "Main street",
                "city": "Heidelberg",
                "country": "DE",
                "zipcode": "ABCDE",
            },
            {"zipcode": ["Enter a zip code in the format XXXXX."]},
            False,
        ),
        # Country with zip code validation implemented directly
        (
            {
                "street": "Main street",
                "city": "Heidelberg",
                "country": "IS",
                "zipcode": "ABCDE",
            },
            {"zipcode": ["Enter a postal code in the format XXX."]},
            False,
        ),
        # Country with zip code normalization inherited from django-localflavor
        (
            {
                "street": "Main street",
                "city": "London",
                "country": "GB",
                "zipcode": "se19de",
            },
            {
                "street": "Main street",
                "city": "London",
                "country": "GB",
                "zipcode": "SE1 9DE",
            },
            False,
        ),
    ],
)
def test_validate_address(input, output, all_optional):
    try:
        actual_output = validate_address(input, all_optional)
    except ValidationError as e:
        assert {
            k: ["".join(s for s in e) for e in v] for k, v in e.error_dict.items()
        } == output
    else:
        if output is True:
            assert actual_output == input
        else:
            assert output == actual_output
