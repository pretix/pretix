# Pretix Widget E2E Tests

End-to-end tests for the pretix widget using Python Playwright and pytest.

## Overview

These tests verify the complete widget experience from a user's perspective, including:
- Widget embedding and initialization
- Product browsing and variations
- Quantity controls and free price inputs
- Cart management and checkout flows
- Iframe/new tab integration
- Responsive behavior and accessibility

## Installation

### Prerequisites

- Python 3.11+
- Virtual environment activated
- Django test database configured

### Setup

1. **Activate the virtual environment:**
   ```bash
   source env/bin/activate
   ```

2. **Install pytest-playwright:**
   ```bash
   pip install pytest-playwright
   ```

3. **Install browser binaries:**
   ```bash
   # Install all browsers (Chromium, Firefox, WebKit)
   python -m playwright install

   # Or install specific browsers only
   python -m playwright install chromium
   python -m playwright install firefox
   ```

4. **Verify installation:**
   ```bash
   pytest src/tests/e2e/ --collect-only
   ```

## Running Tests

### Basic Usage

```bash
# Run all E2E tests
pytest src/tests/e2e/

# Run specific test file
pytest src/tests/e2e/test_widget_embedding.py

# Run specific test
pytest src/tests/e2e/test_widget_cart.py::TestCartBasics::test_add_to_cart_and_open_checkout
```

### Browser Selection

```bash
# Run with specific browser (default: chromium)
pytest src/tests/e2e/ --browser firefox
pytest src/tests/e2e/ --browser webkit

# Run with multiple browsers
pytest src/tests/e2e/ --browser chromium --browser firefox
```

### Debugging Options

```bash
# Show browser UI (headed mode)
pytest src/tests/e2e/ --headed

# Slow down operations for observation (milliseconds)
pytest src/tests/e2e/ --headed --slowmo 1000

# Generate video recordings
pytest src/tests/e2e/ --video on

# Keep browser open on failure
pytest src/tests/e2e/ --headed --pdb

# Generate screenshots on failure
pytest src/tests/e2e/ --screenshot on
```

### Parallel Execution

```bash
# Run tests in parallel (requires pytest-xdist)
pip install pytest-xdist
pytest src/tests/e2e/ -n 4
```

### Verbose Output

```bash
# Show detailed output
pytest src/tests/e2e/ -v

# Show print statements
pytest src/tests/e2e/ -s

# Show all captured output even for passing tests
pytest src/tests/e2e/ -v -s --capture=no
```

## Test Organization

```
src/tests/e2e/
├── conftest.py                    # Shared fixtures and configuration
├── test_widget_embedding.py       # Widget loading and initialization
├── test_widget_variations.py      # Product variations and expansion
├── test_widget_quantity_controls.py  # Quantity inputs, checkboxes, free price
└── test_widget_cart.py            # Cart management and checkout flow
```

### Key Fixtures

Defined in `conftest.py`:

- **`widget_organizer`** - Creates test organizer (testorg)
- **`widget_event`** - Creates test event (testevent)
- **`widget_items`** - Creates General Admission ($50) and VIP Ticket ($150)
- **`widget_item_with_variations`** - Creates t-shirt with S/M/L/XL sizes
- **`widget_item_single_select`** - Creates item with order_max=1 (checkbox)
- **`widget_item_free_price`** - Creates pay-what-you-want donation item
- **`widget_item_sold_out`** - Creates sold out item
- **`widget_event_series`** - Creates event series with 15 subevents
- **`widget_page`** - Enhanced page object with helper methods
- **`live_server_url`** - Django live server URL

### WidgetPage Helper Methods

The `widget_page` fixture provides convenient methods:

```python
def test_example(widget_page, live_server_url, widget_event, widget_items):
    # Navigate to event and wait for widget to load
    widget_page.goto(live_server_url, 'testorg', 'testevent')

    # Select item quantity
    widget_page.select_item_quantity('General Admission', 2)

    # Expand variations
    widget_page.expand_variations('Event T-Shirt')

    # Select variation quantity
    widget_page.select_variation_quantity('Event T-Shirt', 'Medium', 1)

    # Click buy button
    widget_page.click_buy_button()

    # Wait for iframe checkout
    iframe = widget_page.wait_for_iframe_checkout()

    # Close iframe
    widget_page.close_iframe()
```

## Common Test Patterns

### Basic Widget Load Test

```python
@pytest.mark.django_db
def test_widget_loads(page, live_server_url, widget_organizer, widget_event, widget_items, widget_page):
    widget_page.goto(live_server_url, widget_organizer.slug, widget_event.slug)

    # Verify content
    expect(page.locator(f'text="{widget_event.name}"')).to_be_visible()
```

### Variation Interaction Test

```python
@pytest.mark.django_db
def test_variations(page, live_server_url, widget_organizer, widget_event, widget_item_with_variations, widget_page):
    item, variations = widget_item_with_variations

    widget_page.goto(live_server_url, widget_organizer.slug, widget_event.slug)

    # Expand variations
    widget_page.expand_variations(item.name)

    # Verify all variations visible
    for variation in variations:
        expect(page.locator(f'text="{variation.value}"')).to_be_visible()
```

### Cart Flow Test

```python
@pytest.mark.django_db
def test_checkout(page, context, live_server_url, widget_organizer, widget_event, widget_items, widget_page):
    widget_page.goto(live_server_url, widget_organizer.slug, widget_event.slug)

    # Add items
    widget_page.select_item_quantity(widget_items[0].name, 2)
    widget_page.click_buy_button()

    # Wait for checkout to open
    page.wait_for_timeout(2000)

    # Verify cookies set
    cookies = context.cookies()
    assert len(cookies) > 0
```

## Debugging

### View Browser in Action

Run tests with `--headed` flag to see the browser:

```bash
pytest src/tests/e2e/test_widget_embedding.py::TestWidgetEmbedding::test_widget_loads_successfully --headed
```

### Slow Down for Observation

Use `--slowmo` to slow operations (milliseconds):

```bash
pytest src/tests/e2e/ --headed --slowmo 1000
```

### Interactive Debugging

Use `--pdb` to drop into debugger on failure:

```bash
pytest src/tests/e2e/test_widget_cart.py --headed --pdb
```

### Record Videos

Generate video recordings of test runs:

```bash
pytest src/tests/e2e/ --video on

# Videos saved to: test-results/
```

### Generate Trace Files

For detailed debugging with Playwright Inspector:

```bash
pytest src/tests/e2e/ --tracing on

# View traces with:
playwright show-trace test-results/.../trace.zip
```

## Troubleshooting

### Browser binaries not found

**Error:** `playwright._impl._errors.Error: Executable doesn't exist`

**Solution:**
```bash
python -m playwright install chromium
```

### Django database errors

**Error:** `django.db.utils.OperationalError: no such table`

**Solution:**
```bash
# Run migrations in test settings
DJANGO_SETTINGS_MODULE=tests.settings python manage.py migrate
```

### Live server not starting

**Error:** `OSError: [Errno 98] Address already in use`

**Solution:** Kill processes using the port or let pytest assign random ports automatically (default behavior).

### Widget not loading

**Issue:** Widget displays loading spinner indefinitely

**Debug steps:**
1. Check browser console for JavaScript errors:
   ```python
   page.on("console", lambda msg: print(f"Console: {msg.text}"))
   ```

2. Verify widget JavaScript is built:
   ```bash
   ls -l src/pretix/static/pretixpresale/widget/dist/
   ```

3. Check Django static files are served:
   ```bash
   DJANGO_SETTINGS_MODULE=tests.settings python manage.py collectstatic --noinput
   ```

### Timeout errors

**Error:** `playwright._impl._errors.TimeoutError: Timeout 10000ms exceeded`

**Solution:** Increase timeout for specific operations:
```python
page.wait_for_selector('.pretix-widget', timeout=30000)
```

Or globally in conftest.py:
```python
@pytest.fixture
def page(context):
    page = context.new_page()
    page.set_default_timeout(30000)  # 30 seconds
    yield page
    page.close()
```

### Cookie issues

**Issue:** Cart cookies not being set

**Debug:**
```python
# Print all cookies
cookies = context.cookies()
for cookie in cookies:
    print(f"{cookie['name']}: {cookie['value']}")
```

Check domain/path settings match your test server.

## CI/CD Integration

### GitHub Actions Example

```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest-playwright
          python -m playwright install --with-deps chromium

      - name: Run E2E tests
        run: |
          pytest src/tests/e2e/ --browser chromium --video on

      - name: Upload test artifacts
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: test-results
          path: test-results/
```

## Configuration

### setup.cfg

Playwright configuration is in `/home/rash/Projects/pretix/src/setup.cfg`:

```ini
[tool:pytest]
DJANGO_SETTINGS_MODULE = tests.settings
addopts = -rw
# Uncomment for debugging:
# addopts = -rw --headed --slowmo 500
# --browser chromium
```

### Browser Context Args

Customize in `conftest.py`:

```python
@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 720},
        "locale": "en-US",
        "timezone_id": "America/New_York",
    }
```

## Writing New Tests

### Test Structure

```python
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.django_db
class TestFeatureName:
    """Test description."""

    def test_specific_behavior(
        self,
        page: Page,
        live_server_url: str,
        widget_organizer,
        widget_event,
        widget_items,
        widget_page
    ):
        """
        Test should description.

        Given: initial state
        When: action occurs
        Then: expected outcome
        """
        # Arrange
        widget_page.goto(live_server_url, widget_organizer.slug, widget_event.slug)

        # Act
        widget_page.select_item_quantity(widget_items[0].name, 1)

        # Assert
        expect(page.locator('.some-element')).to_be_visible()
```

### Best Practices

1. **Use descriptive test names** - `test_variation_quantity_updates_on_input` vs `test_var`
2. **Use WidgetPage helpers** - Encapsulate common interactions
3. **Wait for elements** - Use `expect().to_be_visible()` instead of `wait_for_timeout()`
4. **Mark Django tests** - Always use `@pytest.mark.django_db` when accessing database
5. **Clean test data** - Use fixtures, let pytest handle cleanup
6. **Verify user-visible behavior** - Test what users see, not implementation details

## Related Documentation

- [Playwright Python Docs](https://playwright.dev/python/)
- [pytest-playwright Plugin](https://github.com/microsoft/playwright-pytest)
- [Pretix Widget Documentation](https://docs.pretix.eu/guides/widget/)
- [Plan Document](/home/rash/.claude/plans/snazzy-wishing-horizon.md) - Complete test specification

## Test Coverage

Current test files cover Phase 1 (Critical Path):

- ✅ Widget embedding & initialization (6 tests)
- ✅ Product variations (7 tests)
- ✅ Quantity controls & free price (11 tests)
- ✅ Cart management & checkout (7 tests)

**Total: 31 tests implemented**

See plan document for complete 130-test specification covering all widget features.
