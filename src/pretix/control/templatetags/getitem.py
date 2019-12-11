from django import template

register = template.Library()


@register.filter(name='getitem')
def getitem_filter(value, itemname):
    if not value:
        return ''

    return value[itemname]
