from django import template
from django.utils import formats
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name='togglesum', needs_autoescape=True)
def cut(value, autoescape=True):
    if not value:
        return ''
    if autoescape:
        esc = conditional_escape
    else:
        esc = lambda x: x
    return mark_safe('<span class="count">{0}</span><span class="sum">{1}</span>'.format(
        esc(value[0]), esc(formats.localize(value[1]))
    ))
