from django import template

from pretix.base.i18n import LazyExpiresDate

register = template.Library()


@register.filter
def format_expires(order):
    return LazyExpiresDate(order.expires.astimezone(order.event.timezone))
