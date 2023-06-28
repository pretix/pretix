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
from markdown import Extension
from markdown.inlinepatterns import SubstituteTagInlineProcessor
from markdown.postprocessors import Postprocessor
from markdown.treeprocessors import UnescapeTreeprocessor
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

DOT_ESCAPE = "|escaped-dot-sGnY9LMK|"


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


class EmailNl2BrExtension(Extension):
    """
    In emails (mostly for backwards-compatibility), we do not follow GitHub Flavored Markdown in preserving newlines.
    Instead, we follow the CommonMark specification:

    "A line ending (not in a code span or HTML tag) that is preceded by two or more spaces and does not occur at the
    end of a block is parsed as a hard line break (rendered in HTML as a <br /> tag)"
    """
    BR_RE = r'  \n'

    def extendMarkdown(self, md):
        br_tag = SubstituteTagInlineProcessor(self.BR_RE, 'br')
        md.inlinePatterns.register(br_tag, 'nl', 5)


class LinkifyPostprocessor(Postprocessor):
    def __init__(self, linker):
        self.linker = linker
        super().__init__()

    def run(self, text):
        return self.linker.linkify(text)


class CleanPostprocessor(Postprocessor):
    def __init__(self, tags, attributes, protocols, strip):
        self.tags = tags
        self.attributes = attributes
        self.protocols = protocols
        self.strip = strip
        super().__init__()

    def run(self, text):
        return bleach.clean(
            text,
            tags=self.tags,
            attributes=self.attributes,
            protocols=self.protocols,
            strip=self.strip
        )


class CustomUnescapeTreeprocessor(UnescapeTreeprocessor):
    """
    This un-escapes everything except \\.
    """

    def _unescape(self, m):
        if m.group(1) == "46":  # 46 is the ASCII position of .
            return DOT_ESCAPE
        return chr(int(m.group(1)))


class CustomUnescapePostprocessor(Postprocessor):
    """
    Restore escaped .
    """

    def run(self, text):
        return text.replace(DOT_ESCAPE, ".")


class LinkifyAndCleanExtension(Extension):
    r"""
    We want to do:

    input --> markdown --> bleach clean --> linkify --> output

    Internally, the markdown library does:

    source --> parse --> (tree|inline)processors --> serializing --> postprocessors

    All escaped characters such as \. will be turned to something like <STX>46<ETX> in the processors
    step and then will be converted to . back again in the last tree processor, before serialization.
    Therefore, linkify does not see the escaped character anymore. This is annoying for the one case
    where you want to type "rich_text.py" and *not* have it turned into a link, since you can't type
    "rich_text\.py" either.

    A simple solution would be to run linkify before markdown, but that may cause other issues when
    linkify messes with the markdown syntax and it makes handling our attributes etc. harder.

    So we do a weird hack where we modify the unescape processor to unescape everything EXCEPT for the
    dot and then unescape that one manually after linkify. However, to make things even harder, the bleach
    clean step removes any invisible characters, so we need to cheat a bit more.
    """

    def __init__(self, linker, tags, attributes, protocols, strip):
        self.linker = linker
        self.tags = tags
        self.attributes = attributes
        self.protocols = protocols
        self.strip = strip
        super().__init__()

    def extendMarkdown(self, md):
        md.treeprocessors.deregister('unescape')
        md.treeprocessors.register(
            CustomUnescapeTreeprocessor(md),
            'unescape',
            0
        )
        md.postprocessors.register(
            CleanPostprocessor(self.tags, self.attributes, self.protocols, self.strip),
            'clean',
            2
        )
        md.postprocessors.register(
            LinkifyPostprocessor(self.linker),
            'linkify',
            1
        )
        md.postprocessors.register(
            CustomUnescapePostprocessor(self.linker),
            'unescape_dot',
            0
        )


def markdown_compile_email(source):
    linker = bleach.Linker(
        url_re=URL_RE,
        email_re=EMAIL_RE,
        callbacks=DEFAULT_CALLBACKS + [truelink_callback, abslink_callback],
        parse_email=True
    )
    return markdown.markdown(
        source,
        extensions=[
            'markdown.extensions.sane_lists',
            EmailNl2BrExtension(),
            LinkifyAndCleanExtension(
                linker,
                tags=ALLOWED_TAGS,
                attributes=ALLOWED_ATTRIBUTES,
                protocols=ALLOWED_PROTOCOLS,
                strip=False,
            )
        ]
    )


class SnippetExtension(markdown.extensions.Extension):
    def extendMarkdown(self, md, *args, **kwargs):
        md.parser.blockprocessors.deregister('olist')
        md.parser.blockprocessors.deregister('ulist')
        md.parser.blockprocessors.deregister('quote')


def markdown_compile(source, linker, snippet=False):
    tags = ALLOWED_TAGS_SNIPPET if snippet else ALLOWED_TAGS
    exts = [
        'markdown.extensions.sane_lists',
        'markdown.extensions.nl2br',
        LinkifyAndCleanExtension(
            linker,
            tags=tags,
            attributes=ALLOWED_ATTRIBUTES,
            protocols=ALLOWED_PROTOCOLS,
            strip=snippet,
        )
    ]
    if snippet:
        exts.append(SnippetExtension())
    return markdown.markdown(
        source,
        extensions=exts
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
    body_md = markdown_compile(text, linker)
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
    body_md = markdown_compile(text, linker, snippet=True)
    return mark_safe(body_md)
