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
from decimal import Decimal

import pytest
from django.template import Context, Template
from django.test import RequestFactory
from django.utils import translation

from pretix.base.templatetags.money import money_filter

TEMPLATE_REPLACE_PAGE = Template(
    "{% load urlreplace %}{% url_replace request 'page' 3 %}"
)
TEMPLATE_MONEY_FILTER = Template("{% load money %}{{ my_amount|money:my_currency }}")
NBSP = "\xa0"


def test_urlreplace_add__first_parameter():
    factory = RequestFactory()
    request = factory.get("/customer/details")
    rendered = TEMPLATE_REPLACE_PAGE.render(Context({"request": request})).strip()
    assert rendered == "page=3"


def test_urlreplace_add_parameter():
    factory = RequestFactory()
    request = factory.get("/customer/details?foo=bar")
    rendered = TEMPLATE_REPLACE_PAGE.render(Context({"request": request})).strip()
    assert rendered in ("foo=bar&amp;page=3", "page=3&amp;foo=bar")


def test_urlreplace_replace_parameter():
    factory = RequestFactory()
    request = factory.get("/customer/details?page=15")
    rendered = TEMPLATE_REPLACE_PAGE.render(Context({"request": request})).strip()
    assert rendered == "page=3"


@pytest.mark.parametrize(
    "locale,amount,currency,expected",
    [
        ("en", None, "USD", "$0.00"),
        ("en", 1000000, "USD", "$1,000,000.00"),
        ("en", Decimal("1000.00"), "USD", "$1,000.00"),
        ("de", Decimal("1.23"), "EUR", "1,23" + NBSP + "€"),
        ("de", Decimal("1000.00"), "EUR", "1.000,00" + NBSP + "€"),
        ("de", Decimal("1023"), "JPY", "1.023" + NBSP + "¥"),

        ("en", Decimal("1023"), "JPY", "¥1,023"),

        # unknown currency
        ("de", Decimal("1234.56"), "FOO", "1.234,56" + NBSP + "FOO"),
        ("de", Decimal("1234.567"), "FOO", "1.234,57" + NBSP + "FOO"),

        # rounding errors
        ("de", Decimal("1.234"), "EUR", "1,23" + NBSP + "€"),
        ("de", Decimal("1023.1"), "JPY", "JPY 1.023,10"),
    ]
)
def test_money_filter(locale, amount, currency, expected):
    factory = RequestFactory()
    translation.activate(locale)
    request = factory.get("/foo/bar")
    rendered = TEMPLATE_MONEY_FILTER.render(
        Context(
            {
                "request": request,
                "my_amount": amount,
                "my_currency": currency,
            }
        )
    ).strip()
    assert rendered == expected


@pytest.mark.parametrize(
    "locale,amount,currency,expected",
    [
        ("de", Decimal("1000.00"), "EUR", "1.000,00"),
        ("en", Decimal("1000.00"), "EUR", "1,000.00"),
        ("de", Decimal("1023.1"), "JPY", "1.023,10"),
    ]
)
def test_money_filter_hidecurrency(locale, amount, currency, expected):
    translation.activate(locale)
    assert money_filter(amount, currency, hide_currency=True) == expected
