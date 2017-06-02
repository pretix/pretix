from django import template
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def prefixtolistprefix(value):
    if not value:
        return ''
    return mark_safe(' '.join(['"{}",'.format(conditional_escape(v)) for v in value.split('-') if v]))
