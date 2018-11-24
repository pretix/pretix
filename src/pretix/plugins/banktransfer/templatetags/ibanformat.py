from django import template

register = template.Library()


@register.filter
def ibanformat(value):
    return ' '.join(value[i:i + 4] for i in range(0, len(value), 4))
