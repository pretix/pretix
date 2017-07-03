from django import template
from django.template.defaulttags import register

@register.filter
def get_item(dictionary, key):
    for t in dictionary:
        if t[0] == key:
            value = t[1]
    return value
