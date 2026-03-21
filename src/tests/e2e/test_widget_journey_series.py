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
class TestEventSeriesJourney:
    """
    Complete purchase journeys for an event series.
    Tests the different views (calendar, list, week) and adds multiple items to the cart.
    """

    def test_multi_subevent_journey_calendar_view(
        self,
        page: Page,
        live_server_url: str,
        organizer,
        event_series,
        widget_page
    ):
        event, _subevents = event_series
        widget_page.goto(
            live_server_url,
            organizer.slug,
            event.slug,
            # **{'list-type': 'list'}
        )
        page.locator('.pretix-widget-event-calendar-event').first.click()

        widget_page.select_item_quantity('Concert Ticket', 2)
        widget_page.click_buy_button()

        iframe = widget_page.wait_for_iframe_checkout()
        expect(
            iframe.locator('text=/45\\.00/').first
        ).to_be_visible(timeout=15000)

        widget_page.close_iframe()
        page.locator('a[rel="back"]').click()

        widget_page.wait_for_view('.pretix-widget-event-calendar-next-month')

        page.locator('.pretix-widget-event-calendar-next-month').click()
        widget_page.wait_for_loading_indicator()
        page.locator('.pretix-widget-event-calendar-event').first.click()

        widget_page.select_item_quantity('Concert Ticket', 1)
        widget_page.click_buy_button()
        iframe = widget_page.wait_for_iframe_checkout()

        # TODO a bit janky selector
        expect(
            iframe.locator('text=/90\\.00/').first
        ).to_be_visible(timeout=15000)

    def test_multi_subevent_journey_list_view(
        self,
        page: Page,
        live_server_url: str,
        organizer,
        event_series,
        widget_page
    ):
        event, _subevents = event_series
        widget_page.goto(
            live_server_url,
            organizer.slug,
            event.slug,
            **{'list-type': 'list'}
        )

        page.locator('.pretix-widget-event-list-entry').first.click()

        widget_page.select_item_quantity('Concert Ticket', 2)
        widget_page.click_buy_button()

        iframe = widget_page.wait_for_iframe_checkout()
        expect(
            iframe.locator('text=/45\\.00/').first
        ).to_be_visible(timeout=15000)

        widget_page.close_iframe()
        page.locator('a[rel="back"]').click()

        widget_page.wait_for_view('.pretix-widget-event-list-entry')

        page.locator('.pretix-widget-event-list-entry').nth(1).click()

        widget_page.select_item_quantity('Concert Ticket', 1)
        widget_page.click_buy_button()
        iframe = widget_page.wait_for_iframe_checkout()

        # TODO a bit janky selector
        expect(
            iframe.locator('text=/90\\.00/').first
        ).to_be_visible(timeout=15000)

    def test_multi_subevent_journey_week_view(
        self,
        page: Page,
        live_server_url: str,
        organizer,
        event_series,
        widget_page
    ):
        event, _subevents = event_series
        widget_page.goto(
            live_server_url,
            organizer.slug,
            event.slug,
            **{'list-type': 'week'}
        )
        page.locator('.pretix-widget-event-calendar-event').first.click()

        widget_page.select_item_quantity('Concert Ticket', 2)
        widget_page.click_buy_button()

        iframe = widget_page.wait_for_iframe_checkout()
        expect(
            iframe.locator('text=/45\\.00/').first
        ).to_be_visible(timeout=15000)

        widget_page.close_iframe()
        page.locator('a[rel="back"]').click()

        widget_page.wait_for_view('.pretix-widget-event-calendar-event')

        page.locator('.pretix-widget-event-calendar-next-month').click()
        widget_page.wait_for_loading_indicator()
        page.locator('.pretix-widget-event-calendar-event').first.click()

        widget_page.select_item_quantity('Concert Ticket', 1)
        widget_page.click_buy_button()
        iframe = widget_page.wait_for_iframe_checkout()

        # TODO a bit janky selector
        expect(
            iframe.locator('text=/90\\.00/').first
        ).to_be_visible(timeout=15000)
