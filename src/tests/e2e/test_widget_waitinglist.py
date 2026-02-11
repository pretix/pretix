"""
E2E Tests for Waiting List Integration

Tests that verify:
- Waiting list link appears for sold out items when enabled
- Waiting list link URL includes correct parameters
"""
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.django_db
class TestWaitingList:
    """Test waiting list display for sold out items."""

    def test_waiting_list_link_appears_when_sold_out(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_sold_out_with_waitinglist,
        widget_page
    ):
        """
        Sold out items with waiting list enabled should show
        a "Waiting list" link.

        Requires:
        - Event setting: waiting_list_enabled = True
        - Item: allow_waitinglist = True
        - Item availability < 100 (sold out)
        """
        item = widget_item_sold_out_with_waitinglist

        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Find the sold out item
        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{item.name}")')
        expect(item_elem).to_be_visible()

        # Should show waiting list link
        waiting_list = item_elem.locator(
            '.pretix-widget-waiting-list-link a')
        expect(waiting_list).to_be_visible()

    def test_waiting_list_link_url_contains_item_id(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_sold_out_with_waitinglist,
        widget_page
    ):
        """
        Waiting list link URL should include item ID parameter.
        """
        item = widget_item_sold_out_with_waitinglist

        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{item.name}")')
        waiting_list_link = item_elem.locator(
            '.pretix-widget-waiting-list-link a')

        href = waiting_list_link.get_attribute('href')
        assert href is not None
        assert f'item={item.pk}' in href
        assert 'waitinglist' in href
