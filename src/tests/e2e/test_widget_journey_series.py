import pytest
from playwright.sync_api import Page, expect


@pytest.mark.django_db
class TestEventSeriesJourney:
    """
    Complete purchase journeys for an event series.
    Tests the different views (calendar, list) and adds multiple items to the cart.
    """

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
        # page.pause()
        page.locator('.pretix-widget-event-list-entry').first.click()

        # expect(
        #     page.locator(
        #         '.pretix-widget-item:has-text("Concert Ticket")')
        # ).to_be_visible(timeout=15000)
        widget_page.select_item_quantity('Concert Ticket', 2)
        widget_page.click_buy_button()

        iframe = widget_page.wait_for_iframe_checkout()
        expect(
            iframe.locator('text=/45\\.00/').first
        ).to_be_visible(timeout=15000)

        # Close iframe and go back to list view
        widget_page.close_iframe()
        page.locator('a[rel="back"]').click()
        # widget_page.goto(
        #     live_server_url,
        #     organizer.slug,
        #     event.slug,
        #     **{'list-type': 'list'}
        # )

        page.locator('.pretix-widget-event-list-entry').nth(1).click()

        # expect(
        #     page.locator('.pretix-widget-item:has-text("Concert Ticket")')
        # ).to_be_visible(timeout=15000)
        # widget_page.select_item_quantity('Concert Ticket', 1)

        # Dispatch change event so the widget detects items are selected
        # (calcItemsSelected listens for 'change', not 'input')
        # page.locator(
        #     '.pretix-widget-item:has-text("Concert Ticket") '
        #     'input[type=number]'
        # ).dispatch_event('change')
        page.pause()
        widget_page.click_buy_button()
        iframe = widget_page.wait_for_iframe_checkout()

        # TODO a bit janky selector
        expect(
            iframe.locator('text=/90\\.00/').first
        ).to_be_visible(timeout=15000)
