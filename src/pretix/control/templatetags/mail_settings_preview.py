from django import template

register = template.Library()


@register.filter(name='split', delimiter=",")
def split(value, delimiter=","):
    return value.split(delimiter)


@register.filter(name="getattr")
def get_attribute(value, key):
    return value[key]
