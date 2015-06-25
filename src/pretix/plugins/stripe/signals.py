from django.core.urlresolvers import resolve
from django.dispatch import receiver
from django.template import Context
from django.template.loader import get_template

from pretix.base.signals import register_payment_providers

from pretix.presale.signals import html_head


@receiver(register_payment_providers)
def register_payment_provider(sender, **kwargs):
    from .payment import Stripe

    return Stripe


@receiver(html_head)
def html_head_presale(sender, request=None, **kwargs):
    from .payment import Stripe

    provider = Stripe(sender)
    url = resolve(request.path_info)
    if provider.is_enabled and ("checkout.payment" in url.url_name or "order.pay" in url.url_name):
        template = get_template('pretixplugins/stripe/presale_head.html')
        ctx = Context({'event': sender, 'settings': provider.settings})
        return template.render(ctx)
    else:
        return ""
