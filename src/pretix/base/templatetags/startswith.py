from django import template
from django.template.defaultfilters import stringfilter

register = template.Library()


@register.filter('startswith')
@stringfilter
def startswith(text, start):
    return text.startswith(start)
