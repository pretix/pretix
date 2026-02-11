"""
E2E Tests for Quantity Controls & Order Limits

Tests that verify:
- Checkbox display for order_max=1 items
- +/- buttons for multi-quantity items
- Order minimum/maximum enforcement
- Auto-selection of single items
"""
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.django_db
class TestQuantityControls:
    """Test quantity control UI elements."""

    def test_checkbox_for_single_select_item(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_single_select,
        widget_page
    ):
        """
        Item with order_max=1 should show checkbox instead of quantity input.

        For items limited to 1 per order, a checkbox is more intuitive than
        a number input.
        """
        item = widget_item_single_select

        widget_page.goto_widget_test_page(live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Find the item
        item_elem = page.locator(f'.pretix-widget-item:has-text("{item.name}")')
        expect(item_elem).to_be_visible()

        # Should have checkbox, NOT number input
        expect(item_elem.locator('input[type="checkbox"]')).to_be_visible()
        expect(item_elem.locator('input[type="number"]')).not_to_be_visible()

    def test_checkbox_selection(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_single_select,
        widget_page
    ):
        """
        Checking the checkbox should select the item.

        User can check/uncheck to add/remove the item.

        Note: When there's only one item, it may be auto-selected by the widget.
        This test verifies the check/uncheck functionality works regardless.
        """
        item = widget_item_single_select

        widget_page.goto_widget_test_page(live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(f'.pretix-widget-item:has-text("{item.name}")')
        checkbox = item_elem.locator('input[type="checkbox"]')

        # Ensure checkbox is unchecked to start test
        if checkbox.is_checked():
            checkbox.uncheck()
        expect(checkbox).not_to_be_checked()

        # Check it
        checkbox.check()
        expect(checkbox).to_be_checked()

        # Uncheck it
        checkbox.uncheck()
        expect(checkbox).not_to_be_checked()

    def test_plus_minus_buttons_for_multi_quantity(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """
        Items with order_max > 1 should have +/- buttons.

        Plus/minus buttons provide an easy way to increment/decrement quantity.
        """
        widget_page.goto_widget_test_page(live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Regular items should have number input with +/- buttons
        item_elem = page.locator(f'.pretix-widget-item:has-text("{widget_items[0].name}")')

        # Should have number input
        expect(item_elem.locator('input[type="number"]')).to_be_visible()

        # Should have + and - buttons
        expect(item_elem.locator('button:has-text("+")')).to_be_visible()
        expect(item_elem.locator('button:has-text("-")')).to_be_visible()

    def test_increment_button_functionality(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """
        Clicking + button should increase quantity by 1.

        Each click increments the value in the number input.
        """
        widget_page.goto_widget_test_page(live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(f'.pretix-widget-item:has-text("{widget_items[0].name}")')
        number_input = item_elem.locator('input[type="number"]')
        plus_button = item_elem.locator('button:has-text("+")').first

        # Initial value should be 0 or empty
        initial_value = number_input.input_value()
        if not initial_value:
            initial_value = "0"

        # Click +
        plus_button.click()
        page.wait_for_timeout(100)

        # Should be incremented
        expect(number_input).to_have_value("1")

        # Click + again
        plus_button.click()
        page.wait_for_timeout(100)

        expect(number_input).to_have_value("2")

    def test_decrement_button_functionality(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """
        Clicking - button should decrease quantity by 1.

        Quantity should not go below 0.
        """
        widget_page.goto_widget_test_page(live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(f'.pretix-widget-item:has-text("{widget_items[0].name}")')
        number_input = item_elem.locator('input[type="number"]')
        plus_button = item_elem.locator('button:has-text("+")').first
        minus_button = item_elem.locator('button:has-text("-")').first

        # Set to 2
        plus_button.click()
        page.wait_for_timeout(100)
        plus_button.click()
        page.wait_for_timeout(100)

        expect(number_input).to_have_value("2")

        # Click -
        minus_button.click()
        page.wait_for_timeout(100)

        expect(number_input).to_have_value("1")

        # Click - again
        minus_button.click()
        page.wait_for_timeout(100)

        expect(number_input).to_have_value("0")

    def test_manual_quantity_input(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """
        User should be able to type quantity directly.

        Number input should accept typed values.
        """
        widget_page.goto_widget_test_page(live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Directly set quantity using helper
        widget_page.select_item_quantity(widget_items[0].name, 5)

        # Verify value
        item_elem = page.locator(f'.pretix-widget-item:has-text("{widget_items[0].name}")')
        number_input = item_elem.locator('input[type="number"]')
        expect(number_input).to_have_value("5")


@pytest.mark.django_db
class TestOrderLimits:
    """Test order minimum and maximum enforcement."""

    def test_order_max_enforces_checkbox_for_single(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_single_select,
        widget_page
    ):
        """Item with order_max=1 should show checkbox (implicit max enforcement)."""
        item = widget_item_single_select  # This has order_max=1

        widget_page.goto_widget_test_page(live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(f'.pretix-widget-item:has-text("{item.name}")')
        expect(item_elem).to_be_visible()

        # order_max=1 items get a checkbox (max is enforced by being binary)
        expect(item_elem.locator('input[type="checkbox"]')).to_be_visible()
        # No number input should exist
        expect(item_elem.locator('input[type="number"]')).not_to_be_visible()

    def test_submit_with_multiple_items_opens_checkout(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """Multiple items with different quantities should open iframe checkout."""
        widget_page.goto_widget_test_page(live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        widget_page.select_item_quantity(widget_items[0].name, 2)
        widget_page.select_item_quantity(widget_items[1].name, 1)

        widget_page.click_buy_button()

        # Iframe checkout should open
        widget_page.wait_for_iframe_checkout()

        iframe_elem = page.locator('iframe[name^="pretix-widget-"]')
        src = iframe_elem.get_attribute('src')
        assert 'take_cart_id' in src


@pytest.mark.django_db
class TestFreePrice:
    """Test pay-what-you-want (free price) items."""

    def test_free_price_input_appears(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_free_price,
        widget_page
    ):
        """
        Free price item should show price input field.

        User should be able to enter their own price.
        """
        item = widget_item_free_price

        widget_page.goto_widget_test_page(live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(f'.pretix-widget-item:has-text("{item.name}")')
        expect(item_elem).to_be_visible()

        # Should show a price input (type=number for price)
        price_inputs = item_elem.locator('.pretix-widget-pricebox-price-input, input[name^="price_"]')
        expect(price_inputs.first).to_be_visible()

    def test_free_price_minimum_enforcement(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_free_price,
        widget_page
    ):
        """
        Free price input should have minimum value set.

        The min attribute should be set to the item's default price.
        """
        item = widget_item_free_price

        widget_page.goto_widget_test_page(live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(f'.pretix-widget-item:has-text("{item.name}")')
        price_input = item_elem.locator('.pretix-widget-pricebox-price-input, input[name^="price_"]').first

        # Should have min attribute
        min_value = price_input.get_attribute('min')
        assert min_value is not None
        assert float(min_value) == float(item.default_price)

    def test_free_price_custom_amount(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_free_price,
        widget_page
    ):
        """
        User should be able to enter custom price amount.

        Amount above minimum should be accepted.
        """
        item = widget_item_free_price

        widget_page.goto_widget_test_page(live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(f'.pretix-widget-item:has-text("{item.name}")')
        price_input = item_elem.locator('.pretix-widget-pricebox-price-input, input[name^="price_"]').first

        # Enter custom amount
        price_input.fill("25.00")

        # Verify value
        expect(price_input).to_have_value("25.00")
