import urllib.parse

import bleach
import markdown
from bleach import DEFAULT_CALLBACKS
from bleach.linkifier import build_email_re, build_url_re
from django import template
from django.conf import settings
from django.core import signing
from django.urls import reverse
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
    # Update doc/user/markdown.rst if you change this!
}

ALLOWED_PROTOCOLS = ['http', 'https', 'mailto', 'tel']

URL_RE = build_url_re(tlds=tld_set)

EMAIL_RE = build_email_re(tlds=tld_set)


def safelink_callback(attrs, new=False):
    url = attrs.get((None, 'href'), '/')
    if not url_has_allowed_host_and_scheme(url, allowed_hosts=None) and not url.startswith('mailto:') and not url.startswith('tel:'):
        signer = signing.Signer(salt='safe-redirect')
        attrs[None, 'href'] = reverse('redirect') + '?url=' + urllib.parse.quote(signer.sign(url))
        attrs[None, 'target'] = '_blank'
        attrs[None, 'rel'] = 'noopener'
    return attrs


def abslink_callback(attrs, new=False):
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


def markdown_compile(source, snippet=False):
    tags = ALLOWED_TAGS_SNIPPET if snippet else ALLOWED_TAGS
    return bleach.clean(
        markdown.markdown(
            source,
            extensions=[
                'markdown.extensions.sane_lists',
                'markdown.extensions.nl2br'
            ]
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
        callbacks=DEFAULT_CALLBACKS + ([safelink_callback] if kwargs.get('safelinks', True) else [abslink_callback]),
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
        callbacks=DEFAULT_CALLBACKS + ([safelink_callback] if kwargs.get('safelinks', True) else [abslink_callback]),
        parse_email=True
    )
    body_md = linker.linkify(markdown_compile(text, snippet=True))
    return mark_safe(body_md)
