"""
E2E Test Configuration for Pretix Widget with Playwright

This module provides pytest fixtures for end-to-end testing of the pretix widget
using Playwright. It integrates Playwright with Django's test infrastructure.
"""

# TODO dev server websocket does not work, but is this relevant?

import os
import subprocess
import pytest
from decimal import Decimal
from datetime import date, datetime, timezone, timedelta
from urllib.request import urlopen
from urllib.error import URLError
from playwright.sync_api import Browser, BrowserContext, Page, expect
from django_scopes import scopes_disabled

from pretix.base.models import (
    Organizer, Event, Item, Quota, ItemVariation, SubEvent, Voucher
)

# Allow Django ORM operations in async context (required for Playwright integration)
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


def _future_dt(days=30, hour=10, minute=0):
    """Build a future UTC datetime with a fixed time-of-day.

    Uses a relative date so tests don't expire, but pins the time
    component so results are deterministic regardless of when tests run.
    """
    d = date.today() + timedelta(days=days)
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=timezone.utc)


# ============================================================================
# Widget Asset Configuration (old Vue2 / new Vite / Vite dev server)
# ============================================================================

PROJECT_ROOT = os.path.join(
    os.path.dirname(__file__),
    '../../..'
)

VITE_DEV_PORT = 5180


@pytest.fixture(scope="session", autouse=True)
def _widget_assets():
    """
    Build or check the widget JS depending on env vars.

    - Default: old Vue2 widget (no build needed)
    - PRETIX_WIDGET_VITE=1: run vite build, Django serves the output
    - PRETIX_WIDGET_VITE_DEV=1: uses your already-running vite dev server
    """
    if os.environ.get("PRETIX_WIDGET_VITE_DEV"):
        try:
            urlopen(f'http://localhost:{VITE_DEV_PORT}/', timeout=2)
        except (URLError, OSError):
            raise RuntimeError(
                f'PRETIX_WIDGET_VITE_DEV is set but no Vite dev server found on port {VITE_DEV_PORT}. '
                f'Start it with: npm run dev:widget'
            )
        yield
    elif os.environ.get("PRETIX_WIDGET_VITE"):
        subprocess.check_call(['npm', 'run', 'build:widget'], cwd=PROJECT_ROOT)
        yield
    else:
        yield  # Old widget, no build needed


# ============================================================================
# Playwright Configuration
# ============================================================================

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Configure browser context for all tests."""
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 720},
        "locale": "en-US",
        "timezone_id": "Europe/Berlin",
        # Enable video recording for debugging (optional)
        # "record_video_dir": "test-results/videos/",
    }


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """Configure browser launch arguments."""
    return {
        **browser_type_launch_args,
        # Uncomment for debugging
        # "headless": False,
        # "slow_mo": 500,  # Slow down operations by 500ms
    }


# ============================================================================
# Django Live Server Fixtures
# ============================================================================

@pytest.fixture
def live_server_url(live_server, settings):
    """
    Get the live server URL.

    Uses pytest-django's built-in live_server fixture which starts
    a Django development server for E2E tests.
    """
    # Enable django-compressor for on-the-fly SCSS compilation
    settings.COMPRESS_ENABLED = True
    settings.COMPRESS_OFFLINE = False  # Compile on-the-fly, not from cache

    # Re-enable SCSS precompilers (disabled in test settings)
    from pretix.testutils.settings import COMPRESS_PRECOMPILERS_ORIGINAL
    settings.COMPRESS_PRECOMPILERS = COMPRESS_PRECOMPILERS_ORIGINAL

    # Fix cache backend for compression
    settings.COMPRESS_CACHE_BACKEND = 'default'

    # Add testcache to CACHES if needed (for compatibility)
    if 'testcache' not in settings.CACHES:
        settings.CACHES['testcache'] = {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }

    settings.SITE_URL = live_server.url

    # Enable Vite widget if requested via env var
    if os.environ.get("PRETIX_WIDGET_VITE") or os.environ.get("PRETIX_WIDGET_VITE_DEV"):
        settings.PRETIX_WIDGET_VITE = True

    return live_server.url

# ============================================================================
# Test Data Fixtures - Organizers and Events
# ============================================================================

@pytest.fixture
@scopes_disabled()
def organizer(db):
    """
    Create an organizer for widget tests.
    Reuses the same pattern as existing API tests.
    """
    return Organizer.objects.create(
        name='Test Organizer',
        slug='testorg',
        plugins='pretix.plugins.banktransfer,pretix.plugins.stripe'
    )


@pytest.fixture
@scopes_disabled()
def event(organizer):
    """Create a basic event for widget tests."""
    event = Event.objects.create(
        organizer=organizer,
        name='Test Event',
        slug='testevent',
        date_from=_future_dt(days=30, hour=10),
        date_to=_future_dt(days=30, hour=18),
        currency='EUR',
        live=True,
        testmode=False,
        plugins='pretix.plugins.banktransfer',
    )
    event.set_defaults()
    event.settings.set('timezone', 'Europe/Berlin')
    event.settings.set('locale', 'en')
    event.settings.set('locales', ['en'])
    return event


@pytest.fixture
@scopes_disabled()
def items(event):
    """Create basic test items/products."""
    from pretix.base.models import ItemCategory

    items = []

    # Create a proper category
    category = ItemCategory.objects.create(
        event=event,
        name='Tickets',
        position=0
    )

    # General Admission ticket
    item1 = Item.objects.create(
        event=event,
        category=category,
        name='General Admission',
        default_price=Decimal('50.00'),
        description='Standard entry ticket',
        active=True,
    )
    items.append(item1)

    # VIP ticket
    item2 = Item.objects.create(
        event=event,
        category=category,
        name='VIP Ticket',
        default_price=Decimal('150.00'),
        description='VIP access with special perks',
        active=True,
    )
    items.append(item2)

    # Create quotas for each item
    for item in items:
        quota = Quota.objects.create(
            event=event,
            name=f'{item.name} Quota',
            size=100,
        )
        quota.items.add(item)

    return items


# ============================================================================
# Test Data Fixtures - Items with Variations
# ============================================================================

@pytest.fixture
@scopes_disabled()
def item_with_variations(event):
    """Create an item with size variations (S, M, L, XL)."""
    from pretix.base.models import ItemCategory

    # Create category for the item
    category = ItemCategory.objects.create(
        event=event,
        name='Merchandise',
        position=1
    )

    item = Item.objects.create(
        event=event,
        category=category,
        name='Event T-Shirt',
        default_price=Decimal('25.00'),
        description='Official event t-shirt',
        active=True,
    )

    variations = []
    sizes_and_prices = [
        ('Small', Decimal('20.00')),
        ('Medium', Decimal('25.00')),
        ('Large', Decimal('25.00')),
        ('X-Large', Decimal('30.00')),
    ]

    for size, price in sizes_and_prices:
        var = ItemVariation.objects.create(
            item=item,
            value=size,
            default_price=price,
        )
        variations.append(var)

    # Create quota for all variations
    quota = Quota.objects.create(
        event=event,
        name='T-Shirt Quota',
        size=50,
    )
    # Add both the item AND the variations to the quota
    quota.items.add(item)
    for var in variations:
        quota.variations.add(var)

    return item, variations


@pytest.fixture
@scopes_disabled()
def item_single_select(event):
    """Create an item with max_per_order=1 (should show checkbox)."""
    from pretix.base.models import ItemCategory

    category = ItemCategory.objects.create(
        event=event,
        name='VIP',
        position=2
    )

    item = Item.objects.create(
        event=event,
        category=category,
        name='VIP Pass',
        default_price=Decimal('500.00'),
        description='Limited VIP pass - one per customer',
        active=True,
        max_per_order=1,
    )

    quota = Quota.objects.create(
        event=event,
        name='VIP Quota',
        size=10,
    )
    quota.items.add(item)

    return item


@pytest.fixture
@scopes_disabled()
def item_free_price(event):
    """Create an item with pay-what-you-want pricing."""
    from pretix.base.models import ItemCategory

    category = ItemCategory.objects.create(
        event=event,
        name='Donations',
        position=3
    )

    item = Item.objects.create(
        event=event,
        category=category,
        name='Donation',
        default_price=Decimal('10.00'),
        description='Support our cause',
        active=True,
        free_price=True,
    )

    quota = Quota.objects.create(
        event=event,
        name='Donation Quota',
        size=999,
    )
    quota.items.add(item)

    return item


@pytest.fixture
@scopes_disabled()
def item_sold_out(event):
    """Create a sold out item."""
    from pretix.base.models import ItemCategory

    category = ItemCategory.objects.create(
        event=event,
        name='Early Bird',
        position=4
    )

    item = Item.objects.create(
        event=event,
        category=category,
        name='Early Bird Ticket',
        default_price=Decimal('30.00'),
        description='Sold out!',
        active=True,
    )

    # Create quota with size=0 (sold out)
    quota = Quota.objects.create(
        event=event,
        name='Early Bird Quota',
        size=0,
    )
    quota.items.add(item)

    return item


@pytest.fixture
@scopes_disabled()
def item_free(event):
    """Create a free item (price = 0.00)."""
    from pretix.base.models import ItemCategory

    category = ItemCategory.objects.create(
        event=event,
        name='Free Stuff',
        position=10
    )

    item = Item.objects.create(
        event=event,
        category=category,
        name='Free Gift',
        default_price=Decimal('0.00'),
        active=True,
    )

    quota = Quota.objects.create(
        event=event,
        name='Free Gift Quota',
        size=100,
    )
    quota.items.add(item)

    return item


@pytest.fixture
@scopes_disabled()
def item_with_decimals(event):
    """Create an item with non-zero decimal price."""
    from pretix.base.models import ItemCategory

    category = ItemCategory.objects.create(
        event=event,
        name='Test Category',
        position=11
    )

    item = Item.objects.create(
        event=event,
        category=category,
        name='Half Price Item',
        default_price=Decimal('12.50'),
        active=True,
    )

    quota = Quota.objects.create(
        event=event,
        name='Half Price Quota',
        size=50,
    )
    quota.items.add(item)

    return item


@pytest.fixture
@scopes_disabled()
def item_with_tax(event):
    """Create an item with tax rule."""
    from pretix.base.models import ItemCategory, TaxRule

    # Create tax rule
    tax_rule = TaxRule.objects.create(
        event=event,
        name='VAT',
        rate=Decimal('19.00'),  # 19% VAT
    )

    category = ItemCategory.objects.create(
        event=event,
        name='Taxed Items',
        position=12
    )

    item = Item.objects.create(
        event=event,
        category=category,
        name='Taxed Product',
        default_price=Decimal('100.00'),
        tax_rule=tax_rule,
        active=True,
    )

    quota = Quota.objects.create(
        event=event,
        name='Taxed Product Quota',
        size=50,
    )
    quota.items.add(item)

    return item


# ============================================================================
# Test Data Fixtures - Edge Cases
# ============================================================================

@pytest.fixture
@scopes_disabled()
def item_min_order(event):
    """Create an item with min_per_order=2."""
    from pretix.base.models import ItemCategory

    category = ItemCategory.objects.create(
        event=event,
        name='Group Tickets',
        position=13
    )

    item = Item.objects.create(
        event=event,
        category=category,
        name='Group Pass',
        default_price=Decimal('40.00'),
        active=True,
        min_per_order=2,
    )

    quota = Quota.objects.create(
        event=event,
        name='Group Pass Quota',
        size=50,
    )
    quota.items.add(item)

    return item


@pytest.fixture
@scopes_disabled()
def item_special_chars(event):
    """Create an item with special characters in the name."""
    from pretix.base.models import ItemCategory

    category = ItemCategory.objects.create(
        event=event,
        name='Spezial',
        position=14
    )

    item = Item.objects.create(
        event=event,
        category=category,
        name='Böhm & Söhne Konzert',
        default_price=Decimal('55.00'),
        active=True,
    )

    quota = Quota.objects.create(
        event=event,
        name='Special Quota',
        size=50,
    )
    quota.items.add(item)

    return item


# ============================================================================
# Test Data Fixtures - Categories
# ============================================================================

@pytest.fixture
@scopes_disabled()
def items_with_category_description(event):
    """Create items with a category that has a description."""
    from pretix.base.models import ItemCategory

    category = ItemCategory.objects.create(
        event=event,
        name='Tickets',
        description='Early bird tickets available',
        position=0
    )

    item = Item.objects.create(
        event=event,
        category=category,
        name='Early Bird',
        default_price=Decimal('35.00'),
        active=True,
    )

    quota = Quota.objects.create(
        event=event,
        name='Early Bird Quota',
        size=100,
    )
    quota.items.add(item)

    return [item]


@pytest.fixture
@scopes_disabled()
def items_multiple_categories(event):
    """Create items in multiple categories to test grouping and ordering."""
    from pretix.base.models import ItemCategory

    cat_music = ItemCategory.objects.create(
        event=event,
        name='Music',
        position=0
    )

    cat_food = ItemCategory.objects.create(
        event=event,
        name='Food & Drink',
        position=1
    )

    item1 = Item.objects.create(
        event=event,
        category=cat_music,
        name='Concert Ticket',
        default_price=Decimal('75.00'),
        active=True,
    )

    item2 = Item.objects.create(
        event=event,
        category=cat_food,
        name='Food Pass',
        default_price=Decimal('25.00'),
        active=True,
    )

    for item in [item1, item2]:
        quota = Quota.objects.create(
            event=event,
            name=f'{item.name} Quota',
            size=100,
        )
        quota.items.add(item)

    return [item1, item2]


# ============================================================================
# Test Data Fixtures - Vouchers
# ============================================================================

@pytest.fixture
@scopes_disabled()
def voucher(event, items):
    """Create a voucher for the event."""
    voucher = Voucher.objects.create(
        event=event,
        code='TESTCODE2024',
        max_usages=10,
        price_mode='none',
    )
    # Clear the vouchers_exist cache so the widget picks it up
    event.get_cache().delete('vouchers_exist')
    return voucher


@pytest.fixture
@scopes_disabled()
def voucher_with_item(event, items):
    """Create a voucher tied to a specific item."""
    item = items[0]
    voucher = Voucher.objects.create(
        event=event,
        code='ITEMVOUCHER',
        max_usages=5,
        price_mode='percent',
        value=Decimal('20.00'),  # 20% off
        item=item,
    )
    event.get_cache().delete('vouchers_exist')
    return voucher


# ============================================================================
# Test Data Fixtures - Waiting List
# ============================================================================

@pytest.fixture
@scopes_disabled()
def item_sold_out_with_waitinglist(event):
    """Create a sold out item with waiting list enabled."""
    from pretix.base.models import ItemCategory

    # Enable waiting list on the event
    event.settings.set('waiting_list_enabled', True)

    category = ItemCategory.objects.create(
        event=event,
        name='Sold Out',
        position=20
    )

    item = Item.objects.create(
        event=event,
        category=category,
        name='Sold Out Concert',
        default_price=Decimal('80.00'),
        active=True,
        allow_waitinglist=True,
    )

    # Create quota with size=0 (sold out)
    quota = Quota.objects.create(
        event=event,
        name='Sold Out Quota',
        size=0,
    )
    quota.items.add(item)

    return item


# ============================================================================
# Test Data Fixtures - Event Series
# ============================================================================

@pytest.fixture
@scopes_disabled()
def event_series(organizer):
    """Create an event series with multiple subevents, items, and quotas."""
    from pretix.base.models import ItemCategory

    event = Event.objects.create(
        organizer=organizer,
        name='Concert Series',
        slug='concert-series',
        date_from=_future_dt(days=30, hour=19),
        has_subevents=True,
        currency='EUR',
        live=True,
        plugins='pretix.plugins.banktransfer',
    )
    event.set_defaults()
    event.settings.set('timezone', 'Europe/Berlin')
    event.settings.set('locale', 'en')
    event.settings.set('locales', ['en'])

    category = ItemCategory.objects.create(
        event=event,
        name='Tickets',
        position=0
    )
    item = Item.objects.create(
        event=event,
        category=category,
        name='Concert Ticket',
        default_price=Decimal('45.00'),
        active=True,
    )

    subevents = []
    base_date = _future_dt(days=30, hour=19)

    for i in range(15):
        se = SubEvent.objects.create(
            event=event,
            name=f'Concert Night {i+1}',
            date_from=base_date + timedelta(days=i*2),
            date_to=base_date + timedelta(days=i*2, hours=2),
            active=True,
        )
        subevents.append(se)

        # Each subevent needs its own quota
        quota = Quota.objects.create(
            event=event,
            name=f'Concert {i+1} Quota',
            size=100,
            subevent=se,
        )
        quota.items.add(item)

    return event, subevents


# ============================================================================
# Widget Helper Fixtures
# ============================================================================

@pytest.fixture
def widget_page(page):
    """
    Enhanced page fixture with widget-specific helper methods.

    Provides convenience methods for common widget interactions.
    """
    class WidgetPage:
        def __init__(self, page: Page):
            self.page = page

        def goto(
            self,
            live_server_url: str,
            org_slug: str,
            event_slug: str,
            wait=True,
            **widget_attrs
        ):
            """
            Navigate to a test page with widget embedded and wait for it to load.

            Uses a Django view that serves an HTML page with the pretix
            widget embedded, simulating how it would be used on a customer's
            website.

            Extra keyword arguments are passed as query params to the view,
            which converts them to widget attributes. For boolean attributes
            (like disable-vouchers), pass an empty string as value.

            Set wait=False to skip waiting for the widget to load (useful for
            tests that need to observe loading/error states).
            """
            # Navigate to the test view URL
            test_url = f"{live_server_url}/widget-test/{org_slug}/{event_slug}/"
            if widget_attrs:
                from urllib.parse import urlencode
                test_url += '?' + urlencode(widget_attrs)
            self.page.goto(test_url)
            if wait:
                self.wait_for_widget_load()
            return self

        def wait_for_widget_load(self):
            """Wait for widget to finish loading."""
            self.page.wait_for_selector('.pretix-widget', timeout=15000)
            # Wait for loading spinner to be hidden (widget has rendered content)
            self.page.locator('.pretix-widget-loading').wait_for(state='hidden', timeout=15000)
            return self

        def wait_for_loading_indicator(self, timeout=15000):
            """Wait for the loading indicator to appear and then disappear (display: none)."""
            loading = self.page.locator('.pretix-widget-loading')
            loading.wait_for(state='visible', timeout=timeout)
            loading.wait_for(state='hidden', timeout=timeout)
            return self

        def select_item_quantity(self, item_name: str, quantity: int):
            """Select quantity for an item by name."""
            # Find the item row
            item_row = self.page.locator(f'.pretix-widget-item:has-text("{item_name}")')

            # Find number input within that row
            number_input = item_row.locator('input[type="number"]').first
            number_input.wait_for(state='visible', timeout=5000)
            if number_input.count() > 0:
                number_input.fill(str(quantity))
                number_input.dispatch_event('change')
            else:
                # Maybe it's a checkbox (order_max=1)
                checkbox = item_row.locator('input[type="checkbox"]').first
                if quantity > 0:
                    checkbox.check()
            return self

        def select_variation_quantity(self, item_name: str, variation_name: str, quantity: int):
            """Select quantity for a specific variation."""
            # Find item
            item = self.page.locator(f'.pretix-widget-item:has-text("{item_name}")')

            # Find variation within item using exact text match to avoid
            # "Large" matching "X-Large"
            variation = item.locator(
                f'.pretix-widget-variation:has(strong:text-is("{variation_name}"))'
            )

            # Find input
            input_field = variation.locator('input[type="number"]').first
            input_field.fill(str(quantity))
            input_field.dispatch_event('change')
            return self

        def click_buy_button(self):
            """Click the buy/register button."""
            buy_button = self.page.locator("""
            .pretix-widget-action button:has-text("Buy"),
            .pretix-widget-action button:has-text("Register")
            """)
            buy_button.first.click()
            return self

        def wait_for_iframe_checkout(self):
            """Wait for checkout iframe to appear."""
            self.page.wait_for_selector('.pretix-widget-frame-shown', timeout=15000)
            # Wait for iframe to load
            self.page.wait_for_function(
                """() => {
                    const iframe = document.querySelector('iframe[name^="pretix-widget-"]');
                    return iframe && iframe.src !== 'about:blank';
                }""",
                timeout=15000
            )
            iframe = self.page.frame_locator('iframe[name^="pretix-widget-"]')
            return iframe

        def close_iframe(self):
            """Close the checkout iframe and wait for the widget to reload.

            The widget triggers a reload() when the iframe is closed
            (without incrementing the loading counter), so we wait for
            the XHR response to complete before returning.
            """
            close_btn = self.page.locator('.pretix-widget-frame-close button')
            # Wait for the reload XHR that fires when the iframe closes
            with self.page.expect_response(
                lambda r: 'widget/product_list' in r.url,
                timeout=15000
            ):
                close_btn.click()
                self.page.locator('.pretix-widget-frame-shown').wait_for(
                    state='detached', timeout=5000
                )
            return self

        def wait_for_view(self, selector: str, timeout=15000):
            """Wait for a specific element to appear after a view switch."""
            self.page.locator(selector).first.wait_for(state='visible', timeout=timeout)
            return self

        def expand_variations(self, item_name: str):
            """Click the 'Show variants' button for an item."""
            item = self.page.locator(f'.pretix-widget-item:has-text("{item_name}")')
            toggle_btn = item.locator('button:has-text("Show variants"), button:has-text("variants")')
            toggle_btn.click()
            return self

        def goto_button_test_page(
            self,
            live_server_url: str,
            org_slug: str,
            event_slug: str,
            **query_params
        ):
            """Navigate to a test page with pretix-button embedded."""
            from urllib.parse import urlencode
            test_url = f"{live_server_url}/button-test/{org_slug}/{event_slug}/"
            if query_params:
                test_url += '?' + urlencode(query_params)
            self.page.goto(test_url)
            return self

    return WidgetPage(page)


# ============================================================================
# Test Data Fixtures - Availability States
# ============================================================================

@pytest.fixture
@scopes_disabled()
def item_require_voucher(event):
    """Create an item that requires a voucher to purchase."""
    from pretix.base.models import ItemCategory

    category = ItemCategory.objects.create(
        event=event,
        name='Voucher Only',
        position=30
    )

    item = Item.objects.create(
        event=event,
        category=category,
        name='Exclusive Pass',
        default_price=Decimal('200.00'),
        active=True,
        require_voucher=True,
    )

    quota = Quota.objects.create(
        event=event,
        name='Exclusive Quota',
        size=50,
    )
    quota.items.add(item)

    return item


@pytest.fixture
@scopes_disabled()
def item_low_stock(event):
    """Create an item with low stock (quota_left visible)."""
    from pretix.base.models import ItemCategory

    category = ItemCategory.objects.create(
        event=event,
        name='Limited',
        position=31
    )

    item = Item.objects.create(
        event=event,
        category=category,
        name='Last Chance Ticket',
        default_price=Decimal('65.00'),
        active=True,
    )

    quota = Quota.objects.create(
        event=event,
        name='Limited Quota',
        size=3,
    )
    quota.items.add(item)

    # Enable "show quota left" on the event
    event.settings.set('show_quota_left', True)

    return item


@pytest.fixture
@scopes_disabled()
def item_not_yet_available(event):
    """Create an item that is not yet available (future available_from)."""
    from pretix.base.models import ItemCategory

    category = ItemCategory.objects.create(
        event=event,
        name='Coming Soon',
        position=32
    )

    item = Item.objects.create(
        event=event,
        category=category,
        name='Future Ticket',
        default_price=Decimal('45.00'),
        active=True,
        available_from=_future_dt(days=365),
        available_from_mode='info',  # Show as "not yet available" instead of hiding
    )

    quota = Quota.objects.create(
        event=event,
        name='Future Quota',
        size=100,
    )
    quota.items.add(item)

    return item


# ============================================================================
# Test Data Fixtures - Items with Pictures
# ============================================================================

@pytest.fixture
@scopes_disabled()
def item_with_picture(event):
    """Create an item with a product picture."""
    from pretix.base.models import ItemCategory
    from django.core.files.uploadedfile import SimpleUploadedFile
    import io
    from PIL import Image as PILImage

    category = ItemCategory.objects.create(
        event=event,
        name='Gallery Items',
        position=40
    )

    # Create a small test image (100x100 red square)
    img = PILImage.new('RGB', (100, 100), color='red')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)

    picture_file = SimpleUploadedFile(
        name='test_product.png',
        content=buf.read(),
        content_type='image/png'
    )

    item = Item.objects.create(
        event=event,
        category=category,
        name='Art Print',
        default_price=Decimal('35.00'),
        description='Limited edition art print',
        active=True,
        picture=picture_file,
    )

    quota = Quota.objects.create(
        event=event,
        name='Art Print Quota',
        size=50,
    )
    quota.items.add(item)

    return item


# ============================================================================
# Cross-Browser Testing
# ============================================================================

@pytest.fixture(params=['chromium'])  # Add 'firefox', 'webkit' when ready
def cross_browser_page(request, playwright):
    """
    Test across multiple browsers.

    Usage:
        def test_widget_works_everywhere(cross_browser_page):
            page = cross_browser_page
            page.goto("...")
    """
    browser_type = getattr(playwright, request.param)
    browser = browser_type.launch()
    context = browser.new_context()
    page = context.new_page()

    yield page

    page.close()
    context.close()
    browser.close()


@pytest.fixture(scope='session', autouse=True)
def _register_widget_test_view():
    """
    Register a test view that serves an HTML page with widget embedded.

    This allows E2E tests to navigate to a real URL instead of using
    set_content, which causes CORS issues.
    """
    from django.http import HttpResponse
    from django.views import View
    from django.urls import path
    from pretix.multidomain import maindomain_urlconf as urls

    class WidgetTestView(View):
        """Serve HTML page with widget embedded for E2E testing."""

        # Widget attributes that can be passed as query params
        WIDGET_ATTRS = [
            'items', 'categories', 'voucher', 'disable-vouchers',
            'disable-iframe', 'subevent', 'list-type',
            'display-event-info', 'skip-ssl-check',
        ]

        def get(self, request, organizer, event):
            base_url = f"{request.scheme}://{request.get_host()}"
            event_url = f"{base_url}/{organizer}/{event}/"
            widget_css = f"{base_url}/{organizer}/{event}/widget/v2.css"

            if os.environ.get("PRETIX_WIDGET_VITE_DEV"):
                script_tag = f'<script type="module" src="http://localhost:{VITE_DEV_PORT}/src/main.ts"></script>'
            else:
                widget_js = f"{base_url}/widget/v2.en.js"
                script_tag = f'<script type="text/javascript" src="{widget_js}" async crossorigin></script>'

            # Build extra attributes from query params
            extra_attrs = ''
            for attr in self.WIDGET_ATTRS:
                val = request.GET.get(attr)
                if val is not None:
                    if val == '':
                        # Boolean attribute (e.g., disable-vouchers)
                        extra_attrs += f' {attr}'
                    else:
                        extra_attrs += f' {attr}="{val}"'

            # Always add skip-ssl-check so iframe checkout works on HTTP
            if 'skip-ssl-check' not in extra_attrs:
                extra_attrs += ' skip-ssl-check'

            html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Widget Test</title>
    <link rel="stylesheet" type="text/css" href="{widget_css}" crossorigin>
  </head>
  <body>
    <pretix-widget event="{event_url}"{extra_attrs}></pretix-widget>
    {script_tag}
</body>
</html>"""
            resp = HttpResponse(html, content_type='text/html')
            resp['Content-Security-Policy'] = "script-src * 'unsafe-inline' 'unsafe-eval'; style-src * 'unsafe-inline'"
            return resp

    class ButtonTestView(View):
        """Serve HTML page with pretix-button element for E2E testing."""

        def get(self, request, organizer, event):
            base_url = f"{request.scheme}://{request.get_host()}"
            event_url = f"{base_url}/{organizer}/{event}/"
            widget_css = f"{base_url}/{organizer}/{event}/widget/v2.css"

            if os.environ.get("PRETIX_WIDGET_VITE_DEV"):
                script_tag = f'<script type="module" src="http://localhost:{VITE_DEV_PORT}/src/main.ts"></script>'
            else:
                widget_js = f"{base_url}/widget/v2.en.js"
                script_tag = f'<script type="text/javascript" src="{widget_js}" async crossorigin></script>'

            # Build extra attributes from query params
            extra_attrs = ''
            for attr in ['items', 'voucher', 'subevent', 'disable-iframe']:
                val = request.GET.get(attr)
                if val is not None:
                    if val == '':
                        extra_attrs += f' {attr}'
                    else:
                        extra_attrs += f' {attr}="{val}"'

            button_text = request.GET.get('button-text', 'Buy tickets!')

            html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Button Test</title>
    <link rel="stylesheet" type="text/css" href="{widget_css}" crossorigin>
</head>
<body>
    <pretix-button event="{event_url}"{extra_attrs}>{button_text}</pretix-button>
    {script_tag}
</body>
</html>"""
            resp = HttpResponse(html, content_type='text/html')
            resp['Content-Security-Policy'] = "script-src * 'unsafe-inline' 'unsafe-eval'; style-src * 'unsafe-inline'"
            return resp

    # Add URL patterns
    test_pattern = path(
        'widget-test/<str:organizer>/<str:event>/',
        WidgetTestView.as_view()
    )
    button_pattern = path(
        'button-test/<str:organizer>/<str:event>/',
        ButtonTestView.as_view()
    )

    # Insert at beginning of URL patterns
    if hasattr(urls, 'urlpatterns'):
        urls.urlpatterns.insert(0, test_pattern)
        urls.urlpatterns.insert(0, button_pattern)
