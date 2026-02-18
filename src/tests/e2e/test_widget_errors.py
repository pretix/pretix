"""
E2E Tests for Error Handling

Tests that verify:
- Error message on invalid event
- Error message shows "Open ticket shop" link
- Sold out items show unavailable state
"""
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.django_db
class TestErrorDisplay:
    """Test error messages and states."""

    def test_invalid_event_shows_error_message(
        self,
        page: Page,
        live_server_url: str,
        organizer,
        event,
        widget_page
    ):
        """
        Loading a non-existent event should show an error message.
        """
        widget_page.goto(
            live_server_url, organizer.slug, 'nonexistent-event')

        # Should show error message
        expect(page.locator(
            '.pretix-widget-error-message'
        )).to_be_visible()

    def test_error_shows_open_in_new_tab_link(
        self,
        page: Page,
        live_server_url: str,
        organizer,
        event,
        widget_page
    ):
        """
        Error state should include a link to open the ticket shop
        in a new tab as a fallback.
        """
        widget_page.goto(
            live_server_url, organizer.slug, 'nonexistent-event')

        # Should show fallback action link
        action_link = page.locator('.pretix-widget-error-action a')
        expect(action_link).to_be_visible()

        # Link should open in new tab
        expect(action_link).to_have_attribute('target', '_blank')


@pytest.mark.django_db
class TestSoldOutState:
    """Test sold out item display."""

    def test_sold_out_item_shows_unavailable(
        self,
        page: Page,
        live_server_url: str,
        organizer,
        event,
        item_sold_out,
        widget_page
    ):
        """
        Items with zero quota should show as unavailable/sold out.
        """
        item = item_sold_out

        widget_page.goto(
            live_server_url, organizer.slug, event.slug)

        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{item.name}")')
        expect(item_elem).to_be_visible()

        # Should not have a quantity input or checkbox (sold out)
        input_count = item_elem.locator(
            'input[type="number"], input[type="checkbox"]').count()
        assert input_count == 0

    def test_sold_out_item_shows_status_text(
        self,
        page: Page,
        live_server_url: str,
        organizer,
        event,
        item_sold_out,
        widget_page
    ):
        """
        Sold out items should show a status message like
        "Sold out" or "Currently unavailable".
        """
        item = item_sold_out

        widget_page.goto(
            live_server_url, organizer.slug, event.slug)

        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{item.name}")')

        # Should show some unavailability text
        avail_col = item_elem.locator(
            '.pretix-widget-item-availability-col')
        expect(avail_col).to_be_visible()
        # The text could be "Sold out", "Currently unavailable", etc.
        avail_text = avail_col.inner_text()
        assert len(avail_text.strip()) > 0
