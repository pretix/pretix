from django import template
from django.conf import settings
from django.template.defaultfilters import floatformat
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name='togglesum', needs_autoescape=True)
def togglesum_filter(value, arg='EUR', autoescape=True):
    def noop(x):
        return x

    if not value:
        return ''
    if autoescape:
        esc = conditional_escape
    else:
        esc = noop

    places = settings.CURRENCY_PLACES.get(arg, 2)
    return mark_safe('<span class="count">{0}</span><span class="sum-gross">{1}</span><span class="sum-net">{2}</span>'.format(
        esc(value[0] if value[0] != 0 else ''),
        esc(floatformat(value[1], places) if value[0] != 0 or value[1] != 0 else ''),
        esc(floatformat(value[2], places) if value[0] != 0 or value[2] != 0 else '')
    ))
