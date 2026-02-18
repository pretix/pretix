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
        organizer,
        event,
        items,
        widget_page
    ):
        """
        When items="<id>" is set, only that item should be shown.
        """
        # Get the first item's ID
        target_item = items[0]
        other_item = items[1]

        widget_page.goto(
            live_server_url,
            organizer.slug,
            event.slug,
            items=str(target_item.pk)
        )

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
        organizer,
        event,
        items,
        widget_page
    ):
        """
        When items="<id1>,<id2>", both items should be shown.
        """
        ids = ','.join(str(item.pk) for item in items)

        widget_page.goto(
            live_server_url,
            organizer.slug,
            event.slug,
            items=ids
        )

        # Both items should be visible
        for item in items:
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
        organizer,
        event,
        items_multiple_categories,
        widget_page
    ):
        """
        When categories="<id>" is set, only items from that category
        should be shown.
        """
        items = items_multiple_categories
        # Get the category of the first item (Music)
        target_category = items[0].category

        widget_page.goto(
            live_server_url,
            organizer.slug,
            event.slug,
            categories=str(target_category.pk)
        )

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
        organizer,
        event,
        voucher,
        widget_page
    ):
        """
        When disable-vouchers is set, voucher input should be hidden
        even when vouchers exist.
        """
        # Navigate with disable-vouchers attribute
        widget_page.goto(
            live_server_url,
            organizer.slug,
            event.slug,
            **{'disable-vouchers': ''}
        )

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
        organizer,
        event,
        items,
        widget_page
    ):
        """
        When disable-iframe is set, checkout should open in a new tab
        instead of an iframe overlay.
        """
        widget_page.goto(
            live_server_url,
            organizer.slug,
            event.slug,
            **{'disable-iframe': ''}
        )

        # Select quantity for an item
        widget_page.select_item_quantity('General Admission', 1)

        # Clicking buy should open a new tab (popup), not an iframe
        with page.expect_popup() as popup_info:
            widget_page.click_buy_button()

        popup = popup_info.value
        # New tab should navigate to checkout URL
        assert organizer.slug in popup.url
        popup.close()
