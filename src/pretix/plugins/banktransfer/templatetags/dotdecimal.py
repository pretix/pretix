from django import template

register = template.Library()


@register.filter
def dotdecimal(value):
    return str(value).replace(",", ".")
