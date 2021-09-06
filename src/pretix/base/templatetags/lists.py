from django import template

register = template.Library()


@register.filter(name='splitlines')
def splitlines(value):
    return value.split("\n")


@register.filter(name='joinlines')
def joinlines(value):
    return "\n".join(value)
