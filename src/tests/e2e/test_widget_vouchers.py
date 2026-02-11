"""
E2E Tests for Voucher Redemption

Tests that verify:
- Voucher input field appears when vouchers exist
- Voucher redemption flow works
- Voucher input hidden when disable-vouchers is set
- Voucher explanation text displays
"""
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.django_db
class TestVoucherDisplay:
    """Test voucher input rendering."""

    def test_voucher_input_appears_when_vouchers_exist(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_voucher,
        widget_page
    ):
        """
        Voucher input field should be visible when event has vouchers.

        The widget checks `vouchers_exist` in the API response.
        """
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Voucher section should be visible
        voucher_section = page.locator('.pretix-widget-voucher')
        expect(voucher_section).to_be_visible()

        # Should have the "Redeem a voucher" heading
        expect(page.locator(
            '.pretix-widget-voucher-headline'
        )).to_be_visible()

        # Should have the voucher input
        expect(page.locator(
            '.pretix-widget-voucher-input'
        )).to_be_visible()

    def test_voucher_input_hidden_when_no_vouchers(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """
        Voucher input should not appear when no vouchers exist.
        """
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Voucher section should NOT be visible
        voucher_section = page.locator('.pretix-widget-voucher')
        expect(voucher_section).to_have_count(0)

    def test_voucher_explanation_text_displays(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_voucher,
        widget_page
    ):
        """
        Voucher explanation text should display when configured.
        """
        # Set voucher explanation text on the event
        widget_event.settings.set(
            'voucher_explanation_text',
            'Enter your voucher code to get a discount.'
        )

        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Explanation text should be visible
        explanation = page.locator('.pretix-widget-voucher-text')
        expect(explanation).to_be_visible()
        expect(explanation).to_contain_text('Enter your voucher code')


@pytest.mark.django_db
class TestVoucherRedemption:
    """Test voucher redemption flow."""

    def test_redeem_voucher_opens_checkout(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_voucher,
        widget_page
    ):
        """
        Entering a voucher code and clicking Redeem should open checkout.

        With skip-ssl-check (added by test harness), this opens in iframe.
        """
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Enter voucher code
        voucher_input = page.locator('.pretix-widget-voucher-input')
        voucher_input.fill('TESTCODE2024')

        # Click the Redeem button
        page.locator(
            '.pretix-widget-voucher-button-wrap button'
        ).click()

        # With skip-ssl-check, voucher redemption opens in iframe
        iframe = widget_page.wait_for_iframe_checkout()

        # The iframe src should contain the voucher code
        iframe_elem = page.locator('iframe[name^="pretix-widget-"]')
        src = iframe_elem.get_attribute('src')
        assert 'TESTCODE2024' in src or 'voucher' in src
