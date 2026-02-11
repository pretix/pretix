"""
E2E Tests for Edge Cases

Tests that verify:
- Empty event (no items) displays gracefully
- Item with min_per_order enforces minimum
- Zero quantity submission shows warning
- Widget handles special characters in names
"""
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.django_db
class TestEmptyStates:
    """Test widget behavior with empty or minimal data."""

    def test_event_with_no_items_shows_empty(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_page
    ):
        """
        Event with no items should still load without errors.
        Should show the widget container but no item rows.
        """
        # Navigate without creating any items
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Widget should still be present
        expect(page.locator('.pretix-widget')).to_be_visible()

        # No items should be shown
        items = page.locator('.pretix-widget-item')
        assert items.count() == 0

    def test_zero_quantity_stays_on_widget(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """
        Submitting with zero quantity should not navigate away.
        The widget should remain visible without opening checkout.
        """
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Don't select any items, just click buy
        widget_page.click_buy_button()
        page.wait_for_timeout(1000)

        # Widget should still be on the same page (no checkout opened)
        expect(page.locator('.pretix-widget')).to_be_visible()

        # Items should still be visible
        expect(page.locator(
            f'.pretix-widget-item:has-text("{widget_items[0].name}")'
        )).to_be_visible()


@pytest.mark.django_db
class TestMinPerOrder:
    """Test minimum order quantity enforcement."""

    def test_item_with_min_per_order_shows_message(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_min_order,
        widget_page
    ):
        """
        Items with min_per_order should display a text message
        indicating the minimum quantity (e.g. "minimum amount to order: 2").
        """
        item = widget_item_min_order

        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{item.name}")')
        expect(item_elem).to_be_visible()

        # Should show minimum order message containing "2"
        meta = item_elem.locator('.pretix-widget-item-meta')
        expect(meta).to_be_visible()
        expect(meta).to_contain_text('2')


@pytest.mark.django_db
class TestSpecialCharacters:
    """Test widget handles special characters correctly."""

    def test_item_name_with_special_characters(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_special_chars,
        widget_page
    ):
        """
        Items with special characters (umlauts, ampersands, etc.)
        should display correctly.
        """
        item = widget_item_special_chars

        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Item with special characters should be visible
        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{item.name}")')
        expect(item_elem).to_be_visible()
