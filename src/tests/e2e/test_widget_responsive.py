"""
E2E Tests for Responsive Behavior

Tests that verify:
- Mobile layout at narrow widths (pretix-widget-mobile class)
- Layout updates on resize
- Desktop layout at wide widths
"""
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.django_db
class TestResponsiveLayout:
    """Test responsive layout behavior."""

    def test_mobile_class_at_narrow_width(
        self,
        page: Page,
        live_server_url: str,
        organizer,
        event,
        items,
        widget_page
    ):
        """
        Widget should add pretix-widget-mobile class when
        container width <= 800px.
        """
        # Set narrow viewport
        page.set_viewport_size({"width": 375, "height": 667})

        widget_page.goto(
            live_server_url, organizer.slug, event.slug)

        # Should have mobile class
        expect(page.locator('.pretix-widget-mobile')).to_be_visible()

    def test_no_mobile_class_at_wide_width(
        self,
        page: Page,
        live_server_url: str,
        organizer,
        event,
        items,
        widget_page
    ):
        """
        Widget should NOT have pretix-widget-mobile class when
        container width > 800px.
        """
        # Ensure wide viewport (default is 1280)
        page.set_viewport_size({"width": 1280, "height": 720})

        widget_page.goto(
            live_server_url, organizer.slug, event.slug)

        # Should NOT have mobile class
        expect(page.locator('.pretix-widget-mobile')).to_have_count(0)

        # But widget itself should be present
        expect(page.locator('.pretix-widget')).to_be_visible()

    def test_responsive_layout_updates_on_resize(
        self,
        page: Page,
        live_server_url: str,
        organizer,
        event,
        items,
        widget_page
    ):
        """
        Widget should switch to mobile layout when browser is resized
        from desktop to mobile width.
        """
        # Start with desktop viewport
        page.set_viewport_size({"width": 1280, "height": 720})

        widget_page.goto(
            live_server_url, organizer.slug, event.slug)

        # Should not be mobile
        expect(page.locator('.pretix-widget-mobile')).to_have_count(0)

        # Resize to mobile
        page.set_viewport_size({"width": 375, "height": 667})

        # Wait for ResizeObserver to fire
        page.wait_for_timeout(500)

        # Should now have mobile class
        expect(page.locator('.pretix-widget-mobile')).to_be_visible()
