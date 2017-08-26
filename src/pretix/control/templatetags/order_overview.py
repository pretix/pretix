from django import template
from django.utils import formats
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name='togglesum', needs_autoescape=True)
def cut(value, autoescape=True):
    def noop(x):
        return x

    if not value:
        return ''
    if autoescape:
        esc = conditional_escape
    else:
        esc = noop
    return mark_safe('<span class="count">{0}</span><span class="sum-gross">{1}</span><span class="sum-net">{2}</span>'.format(
        esc(value[0]), esc(formats.localize(value[1])), esc(formats.localize(value[2]))
    ))
