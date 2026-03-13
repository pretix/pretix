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
