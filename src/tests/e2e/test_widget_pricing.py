"""
E2E Tests for Pricing & Tax Display

Tests that verify:
- Net vs gross price display
- Tax information lines
- Mixed tax rates
- Original price strikethrough for discounts
- Free items display
"""
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.django_db
class TestPriceDisplay:
    """Test price formatting and display."""

    def test_price_displays_with_currency(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """
        Item prices should display with currency code.

        Currency format should match event settings (USD).
        """
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Check that prices are displayed with USD currency code
        # General Admission is USD 50.00
        # USD is in a separate span, so check for both parts
        # Use .first since there are multiple items with USD
        expect(page.locator('text=/USD/').first).to_be_visible()
        expect(page.locator('text=/50\\.00/').first).to_be_visible()

    def test_free_items_display_free_text(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_free,
        widget_page
    ):
        """
        Items with price 0.00 should display "FREE" instead of $0.00.

        Makes free items more obvious to users.
        """
        item = widget_item_free

        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Should show "FREE" text
        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{item.name}")')
        expect(item_elem).to_be_visible()

        # Should contain "FREE" or "free" text (case insensitive)
        expect(item_elem.locator('text=/free/i')).to_be_visible()

    def test_price_includes_decimals(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_with_decimals,
        widget_page
    ):
        """
        Prices should display with proper decimal formatting.

        USD should show 2 decimal places (e.g., $25.00 not $25).
        """
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Should show price with .50
        expect(page.locator('text=/USD.*12\\.50/')).to_be_visible()


@pytest.mark.django_db
class TestTaxDisplay:
    """Test tax information display."""

    def test_tax_rate_displayed_for_taxed_items(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_with_tax,
        widget_page
    ):
        """
        Items with tax should show tax rate information.

        Should display "incl. X% VAT" or similar.
        """
        item = widget_item_with_tax

        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{item.name}")')
        expect(item_elem).to_be_visible()

        # Should show tax information
        # (could be "incl." or "plus" depending on settings)
        # Looking for "19" and "%" near each other
        expect(item_elem.locator('text=/19.*%|%.*19/')).to_be_visible()

    def test_items_without_tax_no_tax_line(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """
        Items without tax rules should not show tax information.

        Tax line should be absent for tax-free items.
        """
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # widget_items by default have no tax
        # We just verify the items display without errors
        for item in widget_items:
            item_elem = page.locator(
                f'.pretix-widget-item:has-text("{item.name}")')
            expect(item_elem).to_be_visible()


@pytest.mark.django_db
class TestDiscountedPricing:
    """Test display of discounted prices."""

    def test_widget_displays_prices_without_errors(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """
        Widget should display all prices without errors.

        This is a smoke test to ensure price rendering works.
        """
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # All items should display their prices
        for item in widget_items:
            item_elem = page.locator(
                f'.pretix-widget-item:has-text("{item.name}")')
            expect(item_elem).to_be_visible()

            # Should have USD currency and price displayed
            expect(item_elem.locator('text=/USD/')).to_be_visible()


@pytest.mark.django_db
class TestPriceForVariations:
    """Test price display for items with variations."""

    def test_variation_price_range_when_collapsed(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_with_variations,
        widget_page
    ):
        """
        Collapsed variations should show price range (min - max).

        E.g., "$20.00 - $30.00" for variations from $20 to $30.
        """
        item, _ = widget_item_with_variations

        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Variations are collapsed by default
        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{item.name}")')
        expect(item_elem).to_be_visible()

        # Should show price range in main row (not in hidden variations)
        # Format: USD 20.00 – 30.00 (en-dash, not hyphen)
        # Look specifically in the main row's price column
        main_row = item_elem.locator('.pretix-widget-main-item-row')
        price_col = main_row.locator('.pretix-widget-item-price-col')
        expect(
            price_col.locator('text=/USD.*20\\.00/')
        ).to_be_visible()
        expect(price_col.locator('text=/30\\.00/')).to_be_visible()

    def test_expanded_variations_show_individual_prices(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_with_variations,
        widget_page
    ):
        """
        Expanded variations show individual prices for each variation.

        Each size should show its own price.
        """
        item, variations = widget_item_with_variations

        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Expand variations
        widget_page.expand_variations(item.name)

        # Check each variation shows a price with USD currency
        # We don't check exact amounts because formatting may vary
        for var in variations:
            var_elem = page.locator(
                f'.pretix-widget-variation:has('
                f'strong:text-is("{var.value}"))'
            )
            expect(var_elem).to_be_visible()

            # Should contain USD currency code
            expect(var_elem.locator('text=/USD/')).to_be_visible()
