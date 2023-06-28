#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
import pytest

from pretix.base.templatetags.rich_text import (
    markdown_compile_email, rich_text, rich_text_snippet,
)


@pytest.mark.parametrize("link", [
    # Test link detection
    ("google.com",
     '<a href="http://google.com" rel="noopener" target="_blank">google.com</a>'),
    # Test link escaping
    ("google\\.com", 'google.com'),
    # Test abslink_callback
    ("[Call](tel:+12345)",
     '<a href="tel:+12345" rel="nofollow">Call</a>'),
    ("[Foo](/foo)",
     '<a href="http://example.com/foo" rel="noopener" target="_blank">Foo</a>'),
    ("mail@example.org",
     '<a href="mailto:mail@example.org">mail@example.org</a>'),
    # Test truelink_callback
    ('evilsite.com',
     '<a href="http://evilsite.com" rel="noopener" target="_blank">evilsite.com</a>'),
    ('cool-example.eu',
     '<a href="http://cool-example.eu" rel="noopener" target="_blank">cool-example.eu</a>'),
    ('<a href="https://evilsite.com">Evil GmbH & Co. KG</a>',
     '<a href="https://evilsite.com" rel="noopener" target="_blank">Evil GmbH &amp; Co. KG</a>'),
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
    ('<a>broken</a>', '<a>broken</a>'),
])
def test_linkify_abs(link):
    input, output = link
    assert rich_text_snippet(input, safelinks=False) == output
    assert rich_text(input, safelinks=False) == f'<p>{output}</p>'
    assert markdown_compile_email(input) == f'<p>{output}</p>'


@pytest.mark.parametrize("content,result", [
    ('a\nb', '<p>a<br>\nb</p>'),
    ('a  \nb', '<p>a<br>\nb</p>'),
    ('a\n\nb', '<p>a</p>\n<p>b</p>'),
])
def test_newline_handling(content, result):
    assert rich_text(content, safelinks=False) == result


@pytest.mark.parametrize("content,result", [
    ('a\nb', '<p>a\nb</p>'),
    ('a  \nb', '<p>a<br>\nb</p>'),
    ('a\n\nb', '<p>a</p>\n<p>b</p>'),
])
def test_newline_handling_email(content, result):
    assert markdown_compile_email(content) == result


@pytest.mark.parametrize("content,result,result_snippet", [
    # attributes
    ('<a onclick="javascript:foo()">foo</a>', '<p><a>foo</a></p>', '<a>foo</a>'),
    ('<strong color="red">foo</strong>',
     '<p><strong>foo</strong></p>',
     '<strong>foo</strong>'),
    # protocols
    ('<a href="javascript:foo()">foo</a>', '<p><a>foo</a></p>', '<a>foo</a>'),
    # tags
    ('<script>foo</script>', '&lt;script&gt;foo&lt;/script&gt;', 'foo'),
])
def test_cleanup(content, result, result_snippet):
    assert rich_text(content) == result
    assert rich_text_snippet(content) == result_snippet
    assert markdown_compile_email(content) == result
