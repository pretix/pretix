from django import template

from pretix.helpers.safedownload import get_token

from ..views.redirect import safelink as sl

register = template.Library()


@register.simple_tag
def safelink(url):
    return sl(url)


@register.simple_tag
def answer_token(request, answer):
    return get_token(request, answer)
