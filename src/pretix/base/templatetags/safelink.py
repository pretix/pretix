from django import template

from ..views.redirect import safelink as sl

register = template.Library()


@register.simple_tag
def safelink(url):
    return sl(url)
