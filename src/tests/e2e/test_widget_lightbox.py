"""
E2E Tests for Item Images & Lightbox

Tests that verify:
- Item with picture shows thumbnail
- Clicking thumbnail opens lightbox overlay
- Lightbox close button works
- Lightbox has correct ARIA structure
"""
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.django_db
class TestItemPicture:
    """Test item picture thumbnail display."""

    def test_item_with_picture_shows_thumbnail(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_with_picture,
        widget_page
    ):
        """Item with picture should display a thumbnail image."""
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{widget_item_with_picture.name}")')
        expect(item_elem).to_be_visible()

        # Should have picture element
        picture = item_elem.locator('.pretix-widget-item-picture')
        expect(picture).to_be_visible()

    def test_item_with_picture_has_alt_text(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_with_picture,
        widget_page
    ):
        """Item picture should have alt text."""
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{widget_item_with_picture.name}")')

        img = item_elem.locator('.pretix-widget-item-picture')
        alt = img.get_attribute('alt')
        assert alt is not None and len(alt) > 0

    def test_item_with_picture_has_link(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_with_picture,
        widget_page
    ):
        """Picture should be wrapped in a clickable link."""
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{widget_item_with_picture.name}")')

        link = item_elem.locator('.pretix-widget-item-picture-link')
        expect(link).to_be_visible()
        href = link.get_attribute('href')
        assert href is not None and len(href) > 0

    def test_item_has_picture_class(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_with_picture,
        widget_page
    ):
        """Item row should have pretix-widget-item-with-picture class."""
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(
            f'.pretix-widget-item-with-picture:has-text("{widget_item_with_picture.name}")')
        expect(item_elem).to_be_visible()


@pytest.mark.django_db
class TestLightbox:
    """Test lightbox overlay for item pictures."""

    def test_click_picture_opens_lightbox(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_with_picture,
        widget_page
    ):
        """Clicking item picture should open lightbox overlay."""
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{widget_item_with_picture.name}")')

        # Click the picture link
        link = item_elem.locator('.pretix-widget-item-picture-link')
        link.click()

        # Lightbox should appear
        lightbox = page.locator('.pretix-widget-lightbox-shown')
        expect(lightbox).to_be_visible()

    def test_lightbox_shows_fullsize_image(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_with_picture,
        widget_page
    ):
        """Lightbox should display fullsize image."""
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{widget_item_with_picture.name}")')
        item_elem.locator('.pretix-widget-item-picture-link').click()

        # Wait for lightbox
        page.wait_for_timeout(1000)

        # Should have an image inside the lightbox
        lightbox_img = page.locator('.pretix-widget-lightbox-image img')
        expect(lightbox_img).to_be_visible()

    def test_lightbox_close_button(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_with_picture,
        widget_page
    ):
        """Lightbox close button should close the overlay."""
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{widget_item_with_picture.name}")')
        item_elem.locator('.pretix-widget-item-picture-link').click()

        # Wait for lightbox to appear
        lightbox = page.locator('.pretix-widget-lightbox-shown')
        expect(lightbox).to_be_visible()

        # Click close button
        close_btn = page.locator('.pretix-widget-lightbox-close button')
        close_btn.click()

        # Lightbox should close
        page.wait_for_timeout(500)
        expect(page.locator('.pretix-widget-lightbox-shown')).not_to_be_visible()

    def test_lightbox_has_alertdialog_role(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_with_picture,
        widget_page
    ):
        """Lightbox dialog should have role='alertdialog'."""
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{widget_item_with_picture.name}")')
        item_elem.locator('.pretix-widget-item-picture-link').click()

        page.wait_for_timeout(1000)

        dialog = page.locator('.pretix-widget-lightbox-holder')
        role = dialog.get_attribute('role')
        assert role == 'alertdialog'
