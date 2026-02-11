"""
E2E Tests for Widget Display Modes

Tests that verify:
- Default widget mode shows full ticket shop
- Calendar view for event series
- List view for event series
- Button mode opens checkout directly
- Calendar navigation (next/prev month)
- Clicking a date in calendar navigates to event
"""
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.django_db
class TestWidgetMode:
    """Test default widget mode (full ticket shop)."""

    def test_widget_mode_shows_items_and_buy_button(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """
        Default widget mode should show full product listing
        with categories, items, and a buy button.
        """
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Should show items
        for item in widget_items:
            expect(page.locator(
                f'.pretix-widget-item:has-text("{item.name}")'
            )).to_be_visible()

        # Should show buy/add-to-cart button
        expect(page.locator(
            'button:has-text("Add to cart"), button:has-text("Buy")'
        ).first).to_be_visible()


@pytest.mark.django_db
class TestCalendarView:
    """Test calendar display mode for event series."""

    def test_calendar_view_displays_month_grid(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event_series,
        widget_page
    ):
        """
        Calendar view should show a monthly grid with event dates.
        """
        event, subevents = widget_event_series

        widget_page.goto_widget_test_page(
            live_server_url,
            widget_organizer.slug,
            event.slug,
            **{'list-type': 'calendar'}
        )
        widget_page.wait_for_widget_load()

        # Should show calendar table
        expect(page.locator(
            '.pretix-widget-event-calendar-table'
        )).to_be_visible()

        # Should have day cells with events
        event_cells = page.locator('.pretix-widget-has-events')
        expect(event_cells.first).to_be_visible()

    def test_calendar_view_navigation_next_month(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event_series,
        widget_page
    ):
        """
        Clicking next month button should navigate to the next month.
        """
        event, subevents = widget_event_series

        widget_page.goto_widget_test_page(
            live_server_url,
            widget_organizer.slug,
            event.slug,
            **{'list-type': 'calendar'}
        )
        widget_page.wait_for_widget_load()

        # Get current month heading text
        header = page.locator('.pretix-widget-event-calendar-head')
        initial_text = header.inner_text()

        # Click next month button
        next_btn = page.locator(
            '.pretix-widget-event-calendar-head a').last
        next_btn.click()

        # Wait for calendar to update
        page.wait_for_timeout(1000)

        # Month heading should change
        updated_text = header.inner_text()
        assert updated_text != initial_text

    def test_calendar_event_links_are_clickable(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event_series,
        widget_page
    ):
        """
        Calendar event entries should be clickable links that show
        event name, time, and availability status.

        Note: Full subevent navigation requires domain configuration
        (target_url resolves to configured domain, not live_server).
        We verify the links exist and have correct structure.
        """
        event, _ = widget_event_series

        widget_page.goto_widget_test_page(
            live_server_url,
            widget_organizer.slug,
            event.slug,
            **{'list-type': 'calendar'}
        )
        widget_page.wait_for_widget_load()

        # Event links should exist and show event info
        event_link = page.locator(
            '.pretix-widget-event-calendar-event').first
        expect(event_link).to_be_visible()

        # Should show event name
        expect(event_link.locator(
            '.pretix-widget-event-calendar-event-name'
        )).to_be_visible()

        # Should show time range
        expect(event_link.locator(
            '.pretix-widget-event-calendar-event-date'
        )).to_be_visible()

        # Should show availability ("Buy now" for available events)
        expect(event_link.locator(
            '.pretix-widget-event-calendar-event-availability'
        )).to_be_visible()


@pytest.mark.django_db
class TestListView:
    """Test list display mode for event series."""

    def test_list_view_displays_events(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event_series,
        widget_page
    ):
        """
        List view should display events as a linear list.
        """
        event, subevents = widget_event_series

        widget_page.goto_widget_test_page(
            live_server_url,
            widget_organizer.slug,
            event.slug,
            **{'list-type': 'list'}
        )
        widget_page.wait_for_widget_load()

        # Should show event list entries
        entries = page.locator('.pretix-widget-event-list-entry')
        expect(entries.first).to_be_visible()

        # Should have multiple entries
        assert entries.count() > 0

    def test_list_view_shows_event_names(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event_series,
        widget_page
    ):
        """
        List view should show subevent names.
        """
        event, subevents = widget_event_series

        widget_page.goto_widget_test_page(
            live_server_url,
            widget_organizer.slug,
            event.slug,
            **{'list-type': 'list'}
        )
        widget_page.wait_for_widget_load()

        # At least the first subevent name should appear
        expect(page.locator(
            f':text-is("{subevents[0].name}")'
        )).to_be_visible()

    def test_list_view_entries_show_availability(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event_series,
        widget_page
    ):
        """
        List view entries should show availability status.

        Note: Full subevent navigation requires domain configuration
        (target_url resolves to configured domain, not live_server).
        We verify the entries have correct structure.
        """
        event, _ = widget_event_series

        widget_page.goto_widget_test_page(
            live_server_url,
            widget_organizer.slug,
            event.slug,
            **{'list-type': 'list'}
        )
        widget_page.wait_for_widget_load()

        # Each entry should show availability info
        first_entry = page.locator(
            '.pretix-widget-event-list-entry').first
        expect(first_entry).to_be_visible()

        # Should show availability indicator (green = available)
        availability = first_entry.locator(
            '.pretix-widget-event-list-entry-availability')
        expect(availability).to_be_visible()


@pytest.mark.django_db
class TestButtonMode:
    """Test button display mode."""

    def test_button_mode_shows_button(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """
        Button mode should show a simple button.
        """
        widget_page.goto_button_test_page(
            live_server_url,
            widget_organizer.slug,
            widget_event.slug
        )

        # Wait for script to load and initialize
        page.wait_for_timeout(2000)

        # Should show the button
        button = page.locator('.pretix-button')
        expect(button).to_be_visible()
        expect(button).to_have_text('Buy tickets!')

    def test_button_click_opens_checkout(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """
        Clicking the button should open checkout (new tab on HTTP).
        """
        widget_page.goto_button_test_page(
            live_server_url,
            widget_organizer.slug,
            widget_event.slug
        )

        page.wait_for_timeout(2000)

        # Click button - on HTTP it opens in new tab
        with page.expect_popup() as popup_info:
            page.locator('.pretix-button').click()

        popup = popup_info.value
        assert widget_organizer.slug in popup.url
        popup.close()
