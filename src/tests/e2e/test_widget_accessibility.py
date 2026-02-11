"""
E2E Tests for Accessibility

Tests that verify:
- ARIA labels on main widget wrapper
- Heading roles and levels
- Voucher input labeling
- Buy button aria-describedby
- Keyboard navigation
- Quantity control labels
- Calendar table accessibility
- Variations toggle aria-expanded/aria-controls
"""
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.django_db
class TestWidgetAriaLabels:
    """Test ARIA attributes on the widget structure."""

    def test_widget_wrapper_has_role_article(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """
        Main widget wrapper should have role="article"
        and aria-label with event name.
        """
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        wrapper = page.locator('.pretix-widget-wrapper')
        expect(wrapper).to_have_attribute('role', 'article')
        expect(wrapper).to_have_attribute('aria-label', widget_event.name)

    def test_widget_wrapper_is_focusable(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """
        Widget wrapper should have tabindex="0" for keyboard access.
        """
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        wrapper = page.locator('.pretix-widget-wrapper')
        expect(wrapper).to_have_attribute('tabindex', '0')

    def test_event_name_has_heading_role(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """
        Event name heading in event form should have role="heading"
        with aria-level="2".

        Note: Event header is only shown when display_event_info
        is explicitly enabled for single events (auto mode hides it).
        We use the display-event-info attribute to force it on.
        """
        widget_page.goto_widget_test_page(
            live_server_url,
            widget_organizer.slug,
            widget_event.slug,
            **{'display-event-info': 'true'}
        )
        widget_page.wait_for_widget_load()

        heading = page.locator(
            '.pretix-widget-event-header strong[role="heading"]')
        expect(heading).to_be_visible()
        expect(heading).to_have_attribute('aria-level', '2')


@pytest.mark.django_db
class TestQuantityControlAccessibility:
    """Test accessibility of quantity controls."""

    def test_increment_button_has_aria_label(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """
        Plus/minus buttons should have descriptive aria-labels.
        """
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Find increment button for first item
        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{widget_items[0].name}")')
        inc_btn = item_elem.locator('button[aria-label]').last
        dec_btn = item_elem.locator('button[aria-label]').first

        # Should have aria-labels
        inc_label = inc_btn.get_attribute('aria-label')
        dec_label = dec_btn.get_attribute('aria-label')
        assert inc_label is not None and len(inc_label) > 0
        assert dec_label is not None and len(dec_label) > 0

    def test_quantity_input_has_aria_labelledby(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """
        Quantity input should be connected to a label via aria-labelledby.
        """
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{widget_items[0].name}")')
        qty_input = item_elem.locator('input[type="number"]')

        labelledby = qty_input.get_attribute('aria-labelledby')
        assert labelledby is not None and len(labelledby) > 0


@pytest.mark.django_db
class TestVoucherAccessibility:
    """Test accessibility of voucher input."""

    def test_voucher_input_has_aria_labelledby(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_voucher,
        widget_page
    ):
        """
        Voucher input should reference the headline via aria-labelledby.
        """
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        voucher_input = page.locator('.pretix-widget-voucher-input')
        headline = page.locator('.pretix-widget-voucher-headline')

        # Headline should have an ID
        headline_id = headline.get_attribute('id')
        assert headline_id is not None

        # Input should reference it
        labelledby = voucher_input.get_attribute('aria-labelledby')
        assert labelledby == headline_id


@pytest.mark.django_db
class TestVariationAccessibility:
    """Test accessibility of variation toggles."""

    def test_variations_toggle_has_aria_expanded(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_item_with_variations,
        widget_page
    ):
        """
        Variations toggle button should have aria-expanded
        and aria-controls attributes.
        """
        item, _ = widget_item_with_variations

        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        item_elem = page.locator(
            f'.pretix-widget-item:has-text("{item.name}")')
        toggle_btn = item_elem.locator(
            'button[aria-expanded]')

        # Should start collapsed
        expect(toggle_btn).to_have_attribute('aria-expanded', 'false')

        # Should reference the variations container
        controls = toggle_btn.get_attribute('aria-controls')
        assert controls is not None

        # Click to expand
        toggle_btn.click()
        expect(toggle_btn).to_have_attribute('aria-expanded', 'true')


@pytest.mark.django_db
class TestCalendarAccessibility:
    """Test accessibility of calendar view."""

    def test_calendar_table_is_focusable(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event_series,
        widget_page
    ):
        """
        Calendar table should have tabindex="0" and aria-labelledby.
        """
        event, _ = widget_event_series

        widget_page.goto_widget_test_page(
            live_server_url,
            widget_organizer.slug,
            event.slug,
            **{'list-type': 'calendar'}
        )
        widget_page.wait_for_widget_load()

        table = page.locator('.pretix-widget-event-calendar-table')
        expect(table).to_have_attribute('tabindex', '0')

        # Should be labeled by the month heading
        labelledby = table.get_attribute('aria-labelledby')
        assert labelledby is not None

    def test_calendar_day_headers_have_aria_labels(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event_series,
        widget_page
    ):
        """
        Calendar day-of-week headers should have full day names
        as aria-labels (Mo -> Monday, Tu -> Tuesday, etc.).
        """
        event, _ = widget_event_series

        widget_page.goto_widget_test_page(
            live_server_url,
            widget_organizer.slug,
            event.slug,
            **{'list-type': 'calendar'}
        )
        widget_page.wait_for_widget_load()

        # Check first day header has aria-label
        first_header = page.locator(
            '.pretix-widget-event-calendar-table thead th').first
        label = first_header.get_attribute('aria-label')
        assert label is not None
        # Should be a full day name like "Monday"
        assert len(label) > 2


@pytest.mark.django_db
class TestKeyboardNavigation:
    """Test keyboard navigation through the widget."""

    def test_tab_reaches_interactive_elements(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """
        Pressing Tab should cycle through interactive elements
        (inputs, buttons) within the widget.
        """
        widget_page.goto_widget_test_page(
            live_server_url, widget_organizer.slug, widget_event.slug)
        widget_page.wait_for_widget_load()

        # Tab through several elements
        focused_tags = set()
        for _ in range(10):
            page.keyboard.press('Tab')
            tag = page.evaluate('() => document.activeElement.tagName')
            focused_tags.add(tag)

        # Should have reached at least inputs and buttons
        assert 'INPUT' in focused_tags or 'BUTTON' in focused_tags
