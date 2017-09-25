import urllib.parse

import bleach
import markdown
from bleach import DEFAULT_CALLBACKS
from django import template
from django.core import signing
from django.urls import reverse
from django.utils.http import is_safe_url
from django.utils.safestring import mark_safe

register = template.Library()

ALLOWED_TAGS = [
    'a',
    'abbr',
    'acronym',
    'b',
    'blockquote',
    'br',
    'code',
    'em',
    'i',
    'li',
    'ol',
    'strong',
    'ul',
    'p',
    'table',
    'tbody',
    'thead',
    'tr',
    'td',
    'th',
    'div',
    'span',
    'h1',
    'h2',
    'h3',
    'h4',
    'h5',
    'h6',
]

ALLOWED_ATTRIBUTES = {
    'a': ['href', 'title'],
    'abbr': ['title'],
    'acronym': ['title'],
    'table': ['width'],
    'td': ['width', 'align'],
    'div': ['class'],
    'p': ['class'],
    'span': ['class'],
}


def safelink_callback(attrs, new=False):
    url = attrs.get((None, 'href'), '/')
    if not is_safe_url(url) and not url.startswith('mailto:'):
        signer = signing.Signer(salt='safe-redirect')
        attrs[None, 'href'] = reverse('redirect') + '?url=' + urllib.parse.quote(signer.sign(url))
        attrs[None, 'target'] = '_blank'
    return attrs


@register.filter
def rich_text(text: str, **kwargs):
    """
    Processes markdown and cleans HTML in a text input.
    """
    text = str(text)
    body_md = bleach.linkify(bleach.clean(
        markdown.markdown(text),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
    ), callbacks=DEFAULT_CALLBACKS + [safelink_callback])
    return mark_safe(body_md)
