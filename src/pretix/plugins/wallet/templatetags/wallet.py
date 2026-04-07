from django import template

from ..models import WalletLayout

register = template.Library()


@register.filter
def platform_layouts(platform, event):
    return WalletLayout.objects.filter(event=event, platform=platform.identifier)
