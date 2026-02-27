from django import template
from django.utils.html import mark_safe

register = template.Library()


@register.filter("anon_email")
def anon_email(value):
    """Replaces @ with [at] and . with [dot] for anonymization."""
    if not isinstance(value, str):
        return value
    value = value.replace("@", "[at]").replace(".", "[dot]")
    return mark_safe(''.join(['&#{0};'.format(ord(char)) for char in value]))
