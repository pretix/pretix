"""
E2E Tests for Widget Configuration Attributes

Tests that verify:
- items attribute filters to specific products
- categories attribute filters by category
- disable-vouchers hides voucher input
- disable-iframe forces new tab checkout
"""
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.django_db
class TestItemsFilter:
    """Test items attribute for filtering products."""

    def test_items_attribute_shows_only_specified_items(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """
        When items="<id>" is set, only that item should be shown.
        """
        # Get the first item's ID
        target_item = widget_items[0]
        other_item = widget_items[1]

        widget_page.goto_widget_test_page(
            live_server_url,
            widget_organizer.slug,
            widget_event.slug,
            items=str(target_item.pk)
        )
        widget_page.wait_for_widget_load()

        # Target item should be visible
        expect(page.locator(
            f'.pretix-widget-item:has-text("{target_item.name}")'
        )).to_be_visible()

        # Other item should NOT be visible
        expect(page.locator(
            f'.pretix-widget-item:has-text("{other_item.name}")'
        )).to_have_count(0)

    def test_items_attribute_with_multiple_ids(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """
        When items="<id1>,<id2>", both items should be shown.
        """
        ids = ','.join(str(item.pk) for item in widget_items)

        widget_page.goto_widget_test_page(
            live_server_url,
            widget_organizer.slug,
            widget_event.slug,
            items=ids
        )
        widget_page.wait_for_widget_load()

        # Both items should be visible
        for item in widget_items:
            expect(page.locator(
                f'.pretix-widget-item:has-text("{item.name}")'
            )).to_be_visible()


@pytest.mark.django_db
class TestCategoriesFilter:
    """Test categories attribute for filtering by category."""

    def test_categories_attribute_shows_only_specified_category(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items_multiple_categories,
        widget_page
    ):
        """
        When categories="<id>" is set, only items from that category
        should be shown.
        """
        items = widget_items_multiple_categories
        # Get the category of the first item (Music)
        target_category = items[0].category

        widget_page.goto_widget_test_page(
            live_server_url,
            widget_organizer.slug,
            widget_event.slug,
            categories=str(target_category.pk)
        )
        widget_page.wait_for_widget_load()

        # Music item should be visible
        expect(page.locator(
            f'.pretix-widget-item:has-text("{items[0].name}")'
        )).to_be_visible()

        # Food item should NOT be visible
        expect(page.locator(
            f'.pretix-widget-item:has-text("{items[1].name}")'
        )).to_have_count(0)


@pytest.mark.django_db
class TestDisableVouchers:
    """Test disable-vouchers attribute."""

    def test_disable_vouchers_hides_voucher_input(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_voucher,
        widget_page
    ):
        """
        When disable-vouchers is set, voucher input should be hidden
        even when vouchers exist.
        """
        # Navigate with disable-vouchers attribute
        widget_page.goto_widget_test_page(
            live_server_url,
            widget_organizer.slug,
            widget_event.slug,
            **{'disable-vouchers': ''}
        )
        widget_page.wait_for_widget_load()

        # Voucher section should NOT be visible
        voucher_section = page.locator('.pretix-widget-voucher')
        expect(voucher_section).to_have_count(0)


@pytest.mark.django_db
class TestDisableIframe:
    """Test disable-iframe attribute."""

    def test_disable_iframe_opens_new_tab(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """
        When disable-iframe is set, checkout should open in a new tab
        instead of an iframe overlay.
        """
        widget_page.goto_widget_test_page(
            live_server_url,
            widget_organizer.slug,
            widget_event.slug,
            **{'disable-iframe': ''}
        )
        widget_page.wait_for_widget_load()

        # Select quantity for an item
        widget_page.select_item_quantity('General Admission', 1)

        # Clicking buy should open a new tab (popup), not an iframe
        with page.expect_popup() as popup_info:
            widget_page.click_buy_button()

        popup = popup_info.value
        # New tab should navigate to checkout URL
        assert widget_organizer.slug in popup.url
        popup.close()
