from django import template

register = template.Library()


@register.filter("anon_email")
def anon_email(value):
    """Replaces @ with [at] and . with [dot] for anonymization."""
    if not isinstance(value, str):
        return value
    return value.replace("@", "[at]").replace(".", "[dot]")
