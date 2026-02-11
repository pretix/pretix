"""
E2E Tests for Product Variations

Tests that verify items with variations (sizes, colors, etc.) work correctly:
- Expand/collapse behavior
- Price ranges
- Individual variation selection
- Auto-expand when filtered
"""
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.django_db
class TestProductVariations:
    """Test product variation functionality."""

    def test_item_with_variations_shows_toggle_button(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_with_variations,
        widget_page
    ):
        """
        Item with variations should show expand/collapse button.

        Variations should be collapsed by default with a button to expand them.
        """
        item, variations = widget_item_with_variations

        widget_page.goto_widget_test_page(live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Should show item name
        expect(page.locator(f'text="{item.name}"')).to_be_visible()

        # Should show variations toggle button
        item_elem = page.locator(f'.pretix-widget-item:has-text("{item.name}")')
        toggle_btn = item_elem.locator('button:has-text("variants"), button:has-text("Show variants")')
        expect(toggle_btn.first).to_be_visible()

    def test_expand_variations_on_click(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_with_variations,
        widget_page
    ):
        """
        Clicking toggle button should expand variations.

        After expanding, all variation options should be visible.
        """
        item, variations = widget_item_with_variations

        widget_page.goto_widget_test_page(live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Expand variations
        widget_page.expand_variations(item.name)

        # Wait for variations to be visible
        page.wait_for_timeout(500)  # Wait for animation

        # All variations should now be visible
        for variation in variations:
            expect(page.locator(f'text="{variation.value}"')).to_be_visible()

    def test_collapse_variations_on_second_click(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_with_variations,
        widget_page
    ):
        """Clicking toggle again should collapse variations."""
        item, variations = widget_item_with_variations

        widget_page.goto_widget_test_page(live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(f'.pretix-widget-item:has-text("{item.name}")')
        toggle_btn = item_elem.locator('button:has-text("variants"), button:has-text("Show variants")')

        # First click - expand
        toggle_btn.first.click()
        page.wait_for_timeout(500)

        # Variations should be visible
        for variation in variations:
            expect(page.locator(f'text="{variation.value}"')).to_be_visible()

        # Second click - collapse
        toggle_btn.first.click()
        page.wait_for_timeout(500)

        # Variation inputs should no longer be visible
        for variation in variations:
            var_row = item_elem.locator(
                f'.pretix-widget-variation:has(strong:text-is("{variation.value}"))')
            expect(var_row.locator('input')).not_to_be_visible()

    def test_price_range_for_collapsed_variations(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_with_variations,
        widget_page
    ):
        """
        Collapsed variations should show price range.

        When variations have different prices, should display range like "$20 - $30".
        """
        item, variations = widget_item_with_variations

        widget_page.goto_widget_test_page(live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Should show price range
        # Variations go from $20 to $30
        item_elem = page.locator(f'.pretix-widget-item:has-text("{item.name}")')

        # Look for price range indicators
        # Format is "USD 20.00 – 30.00" in the main item's price box (first one)
        price_box = item_elem.locator('.pretix-widget-pricebox').first
        expect(price_box).to_contain_text('20.00')
        expect(price_box).to_contain_text('30.00')

    def test_select_variation_quantity(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_with_variations,
        widget_page
    ):
        """
        User should be able to select quantity for specific variation.

        After expanding variations, each should have its own quantity selector.
        """
        item, variations = widget_item_with_variations

        widget_page.goto_widget_test_page(live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Expand variations
        widget_page.expand_variations(item.name)
        page.wait_for_timeout(500)

        # Select quantity for "Medium" variation
        widget_page.select_variation_quantity(item.name, "Medium", 2)

        # Verify input has the value
        medium_var = page.locator('.pretix-widget-variation:has-text("Medium")')
        input_field = medium_var.locator('input[type="number"]')
        expect(input_field).to_have_value("2")

    def test_variation_individual_prices(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_with_variations,
        widget_page
    ):
        """
        Each variation should show its individual price.

        When expanded, variations should display their specific prices.
        """
        item, variations = widget_item_with_variations

        widget_page.goto_widget_test_page(live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Expand variations
        widget_page.expand_variations(item.name)
        page.wait_for_timeout(500)

        # Check each variation shows its price
        variation_prices = {
            'Small': '20.00',
            'Medium': '25.00',
            'Large': '25.00',
            'X-Large': '30.00',
        }

        for var_name, price in variation_prices.items():
            # Use exact heading match to avoid "Large" matching "X-Large"
            var_elem = page.locator(
                f'.pretix-widget-variation:has(strong:text-is("{var_name}"))'
            )
            expect(var_elem).to_be_visible()
            # Price should be visible within the variation element
            expect(var_elem.locator(f'text=/{price}/')).to_be_visible()


@pytest.mark.django_db
class TestVariationSubmission:
    """Test that variation selections submit correctly."""

    def test_submit_with_variation_selection(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_with_variations,
        widget_page
    ):
        """Submitting with a variation selected should open iframe checkout."""
        item, variations = widget_item_with_variations

        widget_page.goto_widget_test_page(live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Expand and select a variation
        widget_page.expand_variations(item.name)
        page.wait_for_timeout(500)
        widget_page.select_variation_quantity(item.name, "Large", 1)

        widget_page.click_buy_button()

        # Iframe checkout should open with the variation in the cart
        widget_page.wait_for_iframe_checkout()

        iframe_elem = page.locator('iframe[name^="pretix-widget-"]')
        src = iframe_elem.get_attribute('src')
        assert 'take_cart_id' in src
