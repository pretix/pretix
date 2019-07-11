import json

from django import template
from django.template.defaultfilters import stringfilter

from pretix.helpers.escapejson import escapejson

register = template.Library()


@register.filter("escapejson")
@stringfilter
def escapejs_filter(value):
    """Hex encodes characters for use in a application/json type script."""
    return escapejson(value)


@register.filter("escapejson_dumps")
def escapejs_dumps_filter(value):
    """Hex encodes characters for use in a application/json type script."""
    return escapejson(json.dumps(value))
