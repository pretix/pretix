from django import template

register = template.Library()


@register.filter(name='split', delimiter=",")
def split(value, delimiter=","):
    return value.split(delimiter)


@register.filter(name="getattr")
def get_attribute(value, key):
    return value[key]


@register.filter(name="hasattr")
def has_attribute(value, key):
    try:
        value[key]
        return True
    except:
        return False
