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
