"""
E2E Tests for Cart Management & Checkout Flow

Tests that verify:
- Adding items to cart opens iframe checkout
- Empty cart does not open checkout
- Cart persistence via cookies
- Resume checkout after page reload
- Multiple item selection
- Mixed input types (checkbox + quantity)
"""
import pytest
from playwright.sync_api import Page, expect, BrowserContext


@pytest.mark.django_db
class TestCartBasics:
    """Test basic cart functionality."""

    def test_add_to_cart_opens_iframe_checkout(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """Selecting items and clicking Buy should open iframe checkout."""
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        widget_page.select_item_quantity(widget_items[0].name, 2)
        widget_page.click_buy_button()

        # Iframe checkout should open
        widget_page.wait_for_iframe_checkout()

        iframe_elem = page.locator('iframe[name^="pretix-widget-"]')
        src = iframe_elem.get_attribute('src')
        assert 'iframe=1' in src
        assert 'take_cart_id' in src

        # page.pause()

    def test_empty_cart_does_not_open_checkout(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """Clicking Buy without selecting items should not open checkout."""
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Don't select any items, just click buy
        widget_page.click_buy_button()
        page.wait_for_timeout(1000)

        # No iframe should have opened
        expect(page.locator('.pretix-widget-frame-shown')).not_to_be_visible()

        # Widget should still be visible (didn't navigate away)
        expect(page.locator('.pretix-widget')).to_be_visible()

        # Items should still be there
        expect(page.locator(
            f'.pretix-widget-item:has-text("{widget_items[0].name}")'
        )).to_be_visible()


@pytest.mark.django_db
class TestCartPersistence:
    """Test cart persistence across page reloads."""

    def test_cart_cookie_set_after_checkout(
        self,
        page: Page,
        context: BrowserContext,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """Adding items to cart should create a pretix_widget cookie."""
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        widget_page.select_item_quantity(widget_items[0].name, 1)
        widget_page.click_buy_button()

        # Wait for iframe checkout to open (cookie is set during cart creation)
        widget_page.wait_for_iframe_checkout()
        page.wait_for_timeout(2000)

        cookies = context.cookies()
        widget_cookies = [c for c in cookies if c['name'].startswith('pretix_widget_')]
        assert len(widget_cookies) > 0, (
            f"Expected pretix_widget cookie after checkout, got: {[c['name'] for c in cookies]}"
        )

    def test_resume_checkout_after_reload(
        self,
        page: Page,
        context: BrowserContext,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """After creating a cart and reloading, widget should show resume option."""
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Create a real cart by adding items and opening checkout
        widget_page.select_item_quantity(widget_items[0].name, 1)
        widget_page.click_buy_button()
        widget_page.wait_for_iframe_checkout()

        # Wait for cart cookie to be set (set in buy_callback when cart is created)
        page.wait_for_function(
            "() => document.cookie.includes('pretix_widget_')",
            timeout=10000
        )

        # Close iframe and reload
        widget_page.close_iframe()
        page.reload()
        widget_page.wait_for_widget_load()

        # Should show "Resume checkout" button (class: pretix-widget-resume-button)
        resume_btn = page.locator('.pretix-widget-resume-button')
        expect(resume_btn).to_be_visible(timeout=5000)


@pytest.mark.django_db
class TestIframeCheckout:
    """Test iframe checkout flow (enabled via skip-ssl-check + SITE_URL fix)."""

    def test_iframe_checkout_opens(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """With skip-ssl-check, checkout should open in iframe on HTTP."""
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        widget_page.select_item_quantity(widget_items[0].name, 1)
        widget_page.click_buy_button()

        widget_page.wait_for_iframe_checkout()

        iframe_elem = page.locator('iframe[name^="pretix-widget-"]')
        src = iframe_elem.get_attribute('src')
        assert 'iframe=1' in src
        assert widget_organizer.slug in src

    def test_close_iframe_button(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """User should be able to close checkout iframe."""
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        widget_page.select_item_quantity(widget_items[0].name, 1)
        widget_page.click_buy_button()

        widget_page.wait_for_iframe_checkout()
        page.wait_for_timeout(3000)

        widget_page.close_iframe()

        expect(page.locator('.pretix-widget-frame-shown')).not_to_be_visible()

    def test_iframe_checkout_has_take_cart_id(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """Iframe checkout URL should include take_cart_id parameter."""
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        widget_page.select_item_quantity(widget_items[0].name, 2)
        widget_page.click_buy_button()

        widget_page.wait_for_iframe_checkout()

        iframe_elem = page.locator('iframe[name^="pretix-widget-"]')
        src = iframe_elem.get_attribute('src')
        assert 'take_cart_id' in src

    def test_overlay_visible_during_checkout(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """Iframe checkout overlay container should be visible during checkout."""
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        widget_page.select_item_quantity(widget_items[0].name, 1)
        widget_page.click_buy_button()

        widget_page.wait_for_iframe_checkout()

        overlay = page.locator('.pretix-widget-frame-holder')
        expect(overlay).to_be_visible()


@pytest.mark.django_db
class TestMultipleItemSelection:
    """Test selecting and submitting multiple items."""

    def test_select_multiple_different_items(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """Selecting multiple items should open checkout with all of them."""
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Select multiple items
        widget_page.select_item_quantity(widget_items[0].name, 2)
        widget_page.select_item_quantity(widget_items[1].name, 1)

        widget_page.click_buy_button()

        # Iframe should open with both items in the cart
        widget_page.wait_for_iframe_checkout()

        iframe_elem = page.locator('iframe[name^="pretix-widget-"]')
        src = iframe_elem.get_attribute('src')
        assert 'take_cart_id' in src

    def test_mixed_checkbox_and_quantity_items(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_item_single_select,
        widget_page
    ):
        """Selecting both checkbox and quantity items should open checkout."""
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Select quantity item
        widget_page.select_item_quantity(widget_items[0].name, 3)

        # Select checkbox item
        widget_page.select_item_quantity(widget_item_single_select.name, 1)

        widget_page.click_buy_button()

        # Iframe should open
        widget_page.wait_for_iframe_checkout()

        iframe_elem = page.locator('iframe[name^="pretix-widget-"]')
        src = iframe_elem.get_attribute('src')
        assert 'take_cart_id' in src
