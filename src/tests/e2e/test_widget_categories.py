"""
E2E Tests for Categories & Organization

Tests that verify:
- Category headers display correctly
- Category descriptions render
- Items are grouped under their respective categories
- Category sort order is maintained
"""
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.django_db
class TestCategoryDisplay:
    """Test category header and description rendering."""

    def test_category_headers_display(
        self,
        page: Page,
        live_server_url: str,
        organizer,
        event,
        items,
        widget_page
    ):
        """
        Category names should be shown as h3 headers.

        The items fixture creates a 'Tickets' category.
        """
        widget_page.goto(
            live_server_url, organizer.slug, event.slug)

        # Category header should be visible
        category_header = page.locator(
            '.pretix-widget-category-name:text-is("Tickets")')
        expect(category_header).to_be_visible()

    def test_category_description_renders(
        self,
        page: Page,
        live_server_url: str,
        organizer,
        event,
        items_with_category_description,
        widget_page
    ):
        """
        Category descriptions should be displayed below category name.
        """
        widget_page.goto(
            live_server_url, organizer.slug, event.slug)

        # Category description should be visible
        desc = page.locator('.pretix-widget-category-description')
        expect(desc.first).to_be_visible()
        expect(desc.first).to_contain_text('Early bird tickets available')

    def test_items_grouped_by_category(
        self,
        page: Page,
        live_server_url: str,
        organizer,
        event,
        items_multiple_categories,
        widget_page
    ):
        """
        Items should be grouped under respective categories
        and maintain category sort order.
        """
        widget_page.goto(
            live_server_url, organizer.slug, event.slug)

        # Both categories should be visible
        expect(page.locator(
            '.pretix-widget-category-name:text-is("Music")'
        )).to_be_visible()
        expect(page.locator(
            '.pretix-widget-category-name:text-is("Food & Drink")'
        )).to_be_visible()

        # Concert Ticket should be under "Music" category
        music_cat = page.locator(
            '.pretix-widget-category:has(.pretix-widget-category-name'
            ':text-is("Music"))')
        expect(music_cat.locator(
            '.pretix-widget-item:has-text("Concert Ticket")'
        )).to_be_visible()

        # Food Pass should be under "Food & Drink" category
        food_cat = page.locator(
            '.pretix-widget-category:has(.pretix-widget-category-name'
            ':text-is("Food & Drink"))')
        expect(food_cat.locator(
            '.pretix-widget-item:has-text("Food Pass")'
        )).to_be_visible()

        # Verify ordering: Music (position=0) should come before
        # Food & Drink (position=1)
        categories = page.locator('.pretix-widget-category-name')
        first_cat = categories.nth(0)
        expect(first_cat).to_have_text('Music')
