import pytest

from pretix.base.templatetags.rich_text import (
    markdown_compile_email, rich_text, rich_text_snippet,
)


@pytest.mark.parametrize("link", [
    # Test link detection
    ("google.com",
     '<a href="http://google.com" rel="noopener" target="_blank">google.com</a>'),
    # Test abslink_callback
    ("[Call](tel:+12345)",
     '<a href="tel:+12345" rel="nofollow">Call</a>'),
    ("[Foo](/foo)",
     '<a href="http://example.com/foo" rel="noopener" target="_blank">Foo</a>'),
    ("mail@example.org",
     '<a href="mailto:mail@example.org">mail@example.org</a>'),
    # Test truelink_callback
    ('<a href="https://evilsite.com">Evil Site</a>',
     '<a href="https://evilsite.com" rel="noopener" target="_blank">Evil Site</a>'),
    ('<a href="https://evilsite.com">evilsite.com</a>',
     '<a href="https://evilsite.com" rel="noopener" target="_blank">evilsite.com</a>'),
    ('<a href="https://evilsite.com">goodsite.com</a>',
     '<a href="https://evilsite.com" rel="noopener" target="_blank">https://evilsite.com</a>'),
    ('<a href="https://goodsite.com.evilsite.com">goodsite.com</a>',
     '<a href="https://goodsite.com.evilsite.com" rel="noopener" target="_blank">https://goodsite.com.evilsite.com</a>'),
    ('<a href="https://evilsite.com/deep/path">evilsite.com</a>',
     '<a href="https://evilsite.com/deep/path" rel="noopener" target="_blank">evilsite.com</a>'),
])
def test_linkify_abs(link):
    input, output = link
    assert rich_text_snippet(input, safelinks=False) == output
    assert rich_text(input, safelinks=False) == f'<p>{output}</p>'
    assert markdown_compile_email(input) == f'<p>{output}</p>'
