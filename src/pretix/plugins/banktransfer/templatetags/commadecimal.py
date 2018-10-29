from django import template

register = template.Library()


@register.filter
def commadecimal(value):
    return str(value).replace(".", ",")
