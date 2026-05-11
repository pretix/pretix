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
from playwright.sync_api import Page, expect


@pytest.mark.django_db
class TestButtonJourney:
    """
    Complete purchase journeys for a regular event.
    Tests item visibility, variation visibility, adding items and variations to cart, and checkout up until showing the iframe.
    """

    def test_no_predefined_items_journey(
        self,
        page: Page,
        live_server_url: str,
        organizer,
        event,
        items,
        widget_page
    ):

        widget_page.goto_button_test_page(
            live_server_url, organizer.slug, event.slug)

        button = page.locator('.pretix-button')
        button.click()
        iframe = widget_page.wait_for_iframe_checkout()

        expect(iframe.locator('#btn-add-to-cart')).to_be_visible(timeout=15000)

    def test_predefined_items_journey(
        self,
        page: Page,
        live_server_url: str,
        organizer,
        event,
        items,
        widget_page
    ):
        item_str = ','.join(f'item_{item.pk}=1' for item in items)

        widget_page.goto_button_test_page(
            live_server_url, organizer.slug, event.slug, items=item_str)

        button = page.locator('.pretix-button')
        button.click()
        iframe = widget_page.wait_for_iframe_checkout()

        # TODO a bit janky selector
        expect(iframe.locator('text=/200\\.00/')).to_be_visible(timeout=15000)

    def test_subevent_button_journey(
        self,
        page: Page,
        live_server_url: str,
        organizer,
        event_series,
        widget_page
    ):
        event, subevents = event_series
        subevent = subevents[2]

        widget_page.goto_button_test_page(
            live_server_url, organizer.slug, event.slug,
            subevent=str(subevent.pk))

        button = page.locator('.pretix-button')
        button.click()
        iframe = widget_page.wait_for_iframe_checkout()

        expect(iframe.locator('#btn-add-to-cart')).to_be_visible(timeout=15000)
        page.pause()
        expect(iframe.get_by_role('heading', name='Concert Night 3')).to_be_visible(timeout=15000)
