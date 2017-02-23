import bleach
import markdown
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

ALLOWED_TAGS = [
    'a',
    'abbr',
    'acronym',
    'b',
    'blockquote',
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
]

ALLOWED_ATTRIBUTES = {
    'a': ['href', 'title'],
    'abbr': ['title'],
    'acronym': ['title'],
    'table': ['width'],
    'td': ['width', 'align'],
}


@register.filter
def rich_text(text: str, **kwargs):
    """
    Processes markdown and cleans HTML in a text input.
    """
    body_md = bleach.linkify(bleach.clean(markdown.markdown(text), tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES))
    return mark_safe(body_md)
