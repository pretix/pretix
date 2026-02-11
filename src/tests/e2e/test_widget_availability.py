"""
E2E Tests for Availability States

Tests that verify:
- Sold out items show "Sold out" message
- Low stock items show "currently available: N"
- Require-voucher items show voucher message
- Not-yet-available items show "Not yet available"
- Available items show quantity selector
"""
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.django_db
class TestSoldOutState:
    """Test sold out availability display."""

    def test_sold_out_shows_message(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_sold_out,
        widget_page
    ):
        """Sold out item should show 'Sold out' text."""
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{widget_item_sold_out.name}")')
        expect(item_elem).to_be_visible()

        # Should show "Sold out" in the availability area
        avail = item_elem.locator('.pretix-widget-availability-gone')
        expect(avail).to_be_visible()

    def test_sold_out_has_no_quantity_selector(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_sold_out,
        widget_page
    ):
        """Sold out item should not show any input controls."""
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{widget_item_sold_out.name}")')
        expect(item_elem).to_be_visible()

        # Should not have any input controls
        assert item_elem.locator('input').count() == 0


@pytest.mark.django_db
class TestQuotaLeftDisplay:
    """Test quota-left indicator for low stock items."""

    def test_low_stock_shows_currently_available(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_low_stock,
        widget_page
    ):
        """
        Item with low stock and show_quota_left should display
        the number of remaining tickets.
        """
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{widget_item_low_stock.name}")')
        expect(item_elem).to_be_visible()

        # Should show quota left text containing "3"
        # The widget uses "currently available: 3" format
        expect(item_elem).to_contain_text('3')

    def test_low_stock_still_has_quantity_selector(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_low_stock,
        widget_page
    ):
        """Low stock items should still be purchasable."""
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{widget_item_low_stock.name}")')
        expect(item_elem).to_be_visible()

        # Should have quantity input
        expect(item_elem.locator('input')).to_be_visible()


@pytest.mark.django_db
class TestRequireVoucherState:
    """Test require-voucher unavailability message."""

    def test_require_voucher_shows_message(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_require_voucher,
        widget_page
    ):
        """Item requiring voucher should show 'Only available with a voucher'."""
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{widget_item_require_voucher.name}")')
        expect(item_elem).to_be_visible()

        # Should show unavailability message with voucher link
        unavail = item_elem.locator('.pretix-widget-availability-unavailable')
        expect(unavail).to_be_visible()
        expect(unavail).to_contain_text('voucher')

    def test_require_voucher_has_link_to_voucher_input(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_require_voucher,
        widget_voucher,
        widget_page
    ):
        """Voucher-required message should link to the voucher input field."""
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{widget_item_require_voucher.name}")')
        unavail = item_elem.locator('.pretix-widget-availability-unavailable')

        # Should have a link (to jump to voucher input)
        link = unavail.locator('a')
        expect(link).to_be_visible()


@pytest.mark.django_db
class TestNotYetAvailable:
    """Test not-yet-available state."""

    def test_future_item_shows_not_yet_available(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_not_yet_available,
        widget_page
    ):
        """Item with future available_from should show 'Not yet available'."""
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{widget_item_not_yet_available.name}")')
        expect(item_elem).to_be_visible()

        # Should show unavailability message
        unavail = item_elem.locator('.pretix-widget-availability-unavailable')
        expect(unavail).to_be_visible()

    def test_future_item_has_no_quantity_selector(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_not_yet_available,
        widget_page
    ):
        """Not-yet-available items should not have quantity controls."""
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{widget_item_not_yet_available.name}")')
        expect(item_elem).to_be_visible()

        # Should not have any input controls
        assert item_elem.locator('input').count() == 0
