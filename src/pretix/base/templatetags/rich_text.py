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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Alexander Schwartz, Tobias Kunze, Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import re
import urllib.parse

import bleach
import markdown
from bleach import DEFAULT_CALLBACKS
from bleach.linkifier import build_email_re, build_url_re
from django import template
from django.conf import settings
from django.core import signing
from django.urls import reverse
from django.utils.functional import SimpleLazyObject
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe
from tlds import tld_set

register = template.Library()

ALLOWED_TAGS_SNIPPET = [
    'a',
    'abbr',
    'acronym',
    'b',
    'br',
    'code',
    'em',
    'i',
    'strong',
    'span',
    # Update doc/user/markdown.rst if you change this!
]
ALLOWED_TAGS = ALLOWED_TAGS_SNIPPET + [
    'blockquote',
    'li',
    'ol',
    'ul',
    'p',
    'table',
    'tbody',
    'thead',
    'tr',
    'td',
    'th',
    'div',
    'hr',
    'h1',
    'h2',
    'h3',
    'h4',
    'h5',
    'h6',
    'pre',
    # Update doc/user/markdown.rst if you change this!
]

ALLOWED_ATTRIBUTES = {
    'a': ['href', 'title', 'class'],
    'abbr': ['title'],
    'acronym': ['title'],
    'table': ['width'],
    'td': ['width', 'align'],
    'div': ['class'],
    'p': ['class'],
    'span': ['class', 'title'],
    'ol': ['start'],
    # Update doc/user/markdown.rst if you change this!
}

ALLOWED_PROTOCOLS = ['http', 'https', 'mailto', 'tel']

URL_RE = SimpleLazyObject(lambda: build_url_re(tlds=sorted(tld_set, key=len, reverse=True)))

EMAIL_RE = SimpleLazyObject(lambda: build_email_re(tlds=sorted(tld_set, key=len, reverse=True)))


def safelink_callback(attrs, new=False):
    """
    Makes sure that all links to a different domain are passed through a redirection handler
    to ensure there's no passing of referers with secrets inside them.
    """
    url = attrs.get((None, 'href'), '/')
    if not url_has_allowed_host_and_scheme(url, allowed_hosts=None) and not url.startswith('mailto:') and not url.startswith('tel:'):
        signer = signing.Signer(salt='safe-redirect')
        attrs[None, 'href'] = reverse('redirect') + '?url=' + urllib.parse.quote(signer.sign(url))
        attrs[None, 'target'] = '_blank'
        attrs[None, 'rel'] = 'noopener'
    return attrs


def truelink_callback(attrs, new=False):
    """
    Tries to prevent "phishing" attacks in which a link looks like it points to a safe place but instead
    points somewhere else, e.g.

        <a href="https://evilsite.com">https://google.com</a>

    At the same time, custom texts are still allowed:

        <a href="https://maps.google.com">Get to the event</a>

    Suffixes are also allowed:

        <a href="https://maps.google.com/location/foo">https://maps.google.com</a>
    """
    text = re.sub(r'[^a-zA-Z0-9.\-/_ ]', '', attrs.get('_text'))  # clean up link text
    url = attrs.get((None, 'href'), '/')
    href_url = urllib.parse.urlparse(url)
    if (None, 'href') in attrs and URL_RE.match(text) and href_url.scheme not in ('tel', 'mailto'):
        # link text looks like a url
        if text.startswith('//'):
            text = 'https:' + text
        elif not text.startswith('http'):
            text = 'https://' + text

        text_url = urllib.parse.urlparse(text)
        if text_url.netloc != href_url.netloc or not href_url.path.startswith(href_url.path):
            # link text contains an URL that has a different base than the actual URL
            attrs['_text'] = attrs[None, 'href']
    return attrs


def abslink_callback(attrs, new=False):
    """
    Makes sure that all links will be absolute links and will be opened in a new page with no
    window.opener attribute.
    """
    if (None, 'href') not in attrs:
        return attrs
    url = attrs.get((None, 'href'), '/')
    if not url.startswith('mailto:') and not url.startswith('tel:'):
        attrs[None, 'href'] = urllib.parse.urljoin(settings.SITE_URL, url)
        attrs[None, 'target'] = '_blank'
        attrs[None, 'rel'] = 'noopener'
    return attrs


def markdown_compile_email(source):
    linker = bleach.Linker(
        url_re=URL_RE,
        email_re=EMAIL_RE,
        callbacks=DEFAULT_CALLBACKS + [truelink_callback, abslink_callback],
        parse_email=True
    )
    return linker.linkify(bleach.clean(
        markdown.markdown(
            source,
            extensions=[
                'markdown.extensions.sane_lists',
                #  'markdown.extensions.nl2br' # disabled for backwards-compatibility
            ]
        ),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
    ))


class SnippetExtension(markdown.extensions.Extension):
    def extendMarkdown(self, md, *args, **kwargs):
        md.parser.blockprocessors.deregister('olist')
        md.parser.blockprocessors.deregister('ulist')
        md.parser.blockprocessors.deregister('quote')


def markdown_compile(source, snippet=False):
    tags = ALLOWED_TAGS_SNIPPET if snippet else ALLOWED_TAGS
    exts = [
        'markdown.extensions.sane_lists',
        'markdown.extensions.nl2br'
    ]
    if snippet:
        exts.append(SnippetExtension())
    return bleach.clean(
        markdown.markdown(
            source,
            extensions=exts
        ),
        strip=snippet,
        tags=tags,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
    )


@register.filter
def rich_text(text: str, **kwargs):
    """
    Processes markdown and cleans HTML in a text input.
    """
    text = str(text)
    linker = bleach.Linker(
        url_re=URL_RE,
        email_re=EMAIL_RE,
        callbacks=DEFAULT_CALLBACKS + ([truelink_callback, safelink_callback] if kwargs.get('safelinks', True) else [truelink_callback, abslink_callback]),
        parse_email=True
    )
    body_md = linker.linkify(markdown_compile(text))
    return mark_safe(body_md)


@register.filter
def rich_text_snippet(text: str, **kwargs):
    """
    Processes markdown and cleans HTML in a text input.
    """
    text = str(text)
    linker = bleach.Linker(
        url_re=URL_RE,
        email_re=EMAIL_RE,
        callbacks=DEFAULT_CALLBACKS + ([truelink_callback, safelink_callback] if kwargs.get('safelinks', True) else [truelink_callback, abslink_callback]),
        parse_email=True
    )
    body_md = linker.linkify(markdown_compile(text, snippet=True))
    return mark_safe(body_md)
