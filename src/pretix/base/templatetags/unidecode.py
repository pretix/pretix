import text_unidecode
from django import template

register = template.Library()


@register.filter
def unidecode(value):
    return text_unidecode.unidecode(str(value))
