"""
Test to verify CSS is properly compiled without SCSS syntax.
"""
import pytest
from playwright.sync_api import Page


@pytest.mark.django_db
def test_css_contains_no_scss_syntax(
    page: Page,
    live_server_url: str,
    widget_organizer,
    widget_event,
    widget_items
):
    """Verify CSS is compiled and doesn't contain SCSS syntax."""
    # Fetch the CSS directly
    css_url = f"{live_server_url}/{widget_organizer.slug}/{widget_event.slug}/widget/v2.css"

    print(f"\nFetching CSS from: {css_url}")
    response = page.request.get(css_url)

    print(f"Status: {response.status}")
    assert response.status == 200, f"CSS returned {response.status}"

    css_content = response.text()

    # Check that CSS doesn't contain SCSS syntax
    scss_indicators = [
        '@include',  # SCSS mixins
        '@extend',   # SCSS extends
        '$',         # SCSS variables (though $ can appear in selectors, check more carefully)
    ]

    print(f"\nCSS length: {len(css_content)} characters")
    print(f"\nFirst 500 chars of CSS:\n{css_content[:500]}")

    has_scss = False
    for indicator in scss_indicators:
        if indicator in css_content:
            # For $, be more specific - check if it's actually a variable
            if indicator == '$':
                # Look for variable patterns like $variable-name or $variable_name
                import re
                if re.search(r'\$[a-zA-Z_]', css_content):
                    has_scss = True
                    print(f"\n⚠️  Found SCSS syntax: {indicator}")
                    # Find and print examples
                    matches = re.findall(r'\$[a-zA-Z_][a-zA-Z0-9_-]*', css_content)
                    print(f"Examples: {matches[:5]}")
            else:
                has_scss = True
                print(f"\n⚠️  Found SCSS syntax: {indicator}")
                # Find line with the indicator
                for i, line in enumerate(css_content.split('\n')[:100]):
                    if indicator in line:
                        print(f"Line {i+1}: {line}")
                        break

    if not has_scss:
        print("\n✅ CSS is properly compiled - no SCSS syntax found!")

    assert not has_scss, "CSS contains SCSS syntax - not properly compiled!"
