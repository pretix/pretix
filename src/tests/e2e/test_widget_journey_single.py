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
class TestSingleEventJourney:
    """
    Complete purchase journeys for a regular event.
    Tests item visibility, variation visibility, adding items and variations to cart, and checkout up until showing the iframe.
    """

    def test_full_purchase_journey(
        self,
        page: Page,
        live_server_url: str,
        organizer,
        event,
        items,
        widget_page
    ):

        widget_page.goto(
            live_server_url, organizer.slug, event.slug)

        ga_item = page.locator('.pretix-widget-item:has-text("General Admission")')
        expect(ga_item).to_be_visible()
        expect(ga_item.locator('text=/50\\.00/')).to_be_visible()

        vip_item = page.locator('.pretix-widget-item:has-text("VIP Ticket")')
        expect(vip_item).to_be_visible()
        expect(vip_item.locator('text=/150\\.00/')).to_be_visible()

        widget_page.select_item_quantity('General Admission', 2)
        widget_page.select_item_quantity('VIP Ticket', 1)

        widget_page.click_buy_button()
        iframe = widget_page.wait_for_iframe_checkout()

        # TODO a bit janky selector
        expect(iframe.locator('text=/250\\.00/')).to_be_visible(timeout=15000)

    def test_journey_with_variations(
        self,
        page: Page,
        live_server_url: str,
        organizer,
        event,
        items,
        item_with_variations,
        widget_page
    ):
        item, _variations = item_with_variations

        widget_page.goto(
            live_server_url, organizer.slug, event.slug)

        item_elem = page.locator(f'.pretix-widget-item:has-text("{item.name}")')
        expect(item_elem).to_be_visible()

        widget_page.expand_variations(item.name)
        large_var = page.locator('.pretix-widget-variation:has(strong:text-is("Large"))')
        expect(large_var).to_be_visible()
        expect(large_var.locator('text=/25\\.00/')).to_be_visible()

        widget_page.select_item_quantity('General Admission', 1)
        widget_page.select_variation_quantity(item.name, 'Large', 1)

        widget_page.click_buy_button()
        iframe = widget_page.wait_for_iframe_checkout()

        # TODO a bit janky selector
        expect(iframe.locator('text=/75\\.00/')).to_be_visible(timeout=15000)
