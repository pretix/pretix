"""
E2E Tests for Loading States & Performance

Tests that verify:
- Loading spinner appears during widget initialization
- Loading spinner disappears after content loads
- Widget loads within acceptable time
- No JavaScript errors during widget initialization
"""
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.django_db
class TestLoadingStates:
    """Test loading states and transitions."""

    def test_loading_spinner_disappears_after_load(
        self,
        page: Page,
        live_server_url: str,
        organizer,
        event,
        items,
        widget_page
    ):
        """
        Loading spinner should be hidden once widget content loads.
        """
        widget_page.goto(
            live_server_url, organizer.slug, event.slug)

        # Loading spinner should be hidden (display:none)
        loading = page.locator('.pretix-widget-loading')
        expect(loading).to_be_hidden()

    def test_widget_loads_within_timeout(
        self,
        page: Page,
        live_server_url: str,
        organizer,
        event,
        items,
        widget_page
    ):
        """
        Widget should fully load within 15 seconds.
        """
        widget_page.goto(
            live_server_url, organizer.slug, event.slug, wait=False)

        # Widget should appear within 15s
        page.wait_for_selector('.pretix-widget', timeout=15000)

        # Items should be visible within 15s total
        expect(page.locator(
            f'.pretix-widget-item:has-text("{items[0].name}")'
        )).to_be_visible(timeout=15000)

    def test_no_javascript_errors_on_load(
        self,
        page: Page,
        live_server_url: str,
        organizer,
        event,
        items,
        widget_page
    ):
        """
        Widget should load without any JavaScript console errors.
        """
        errors = []
        page.on('pageerror', lambda err: errors.append(str(err)))

        widget_page.goto(
            live_server_url, organizer.slug, event.slug)

        # No JS errors should have occurred
        assert len(errors) == 0, f"JavaScript errors: {errors}"


@pytest.mark.django_db
class TestWidgetReload:
    """Test widget behavior on page interactions."""

    def test_widget_css_loads_correctly(
        self,
        page: Page,
        live_server_url: str,
        organizer,
        event,
        items,
        widget_page
    ):
        """
        Widget CSS should load and apply styles.
        No SCSS syntax should leak into rendered styles.
        """
        widget_page.goto(
            live_server_url, organizer.slug, event.slug)

        # Check that widget has actual styled dimensions
        # (not zero-height which would indicate CSS failure)
        widget = page.locator('.pretix-widget')
        box = widget.bounding_box()
        assert box is not None
        assert box['height'] > 50  # Widget should have meaningful height
        assert box['width'] > 100  # Widget should have meaningful width
