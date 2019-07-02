import logging
from urllib.parse import urlsplit

import stripe
from django.conf import settings

from pretix.base.services.tasks import EventTask
from pretix.celery_app import app
from pretix.multidomain.urlreverse import get_domain
from pretix.plugins.stripe.models import RegisteredApplePayDomain

logger = logging.getLogger(__name__)


def get_domain_for_event(event):
    domain = get_domain(event.organizer)
    if not domain:
        siteurlsplit = urlsplit(settings.SITE_URL)
        return siteurlsplit.hostname
    return domain


def get_stripe_account_key(prov):
    if prov.settings.connect_user_id:
        return prov.settings.connect_user_id
    else:
        return prov.settings.publishable_key


@app.task(base=EventTask, max_retries=5, default_retry_delay=1)
def stripe_verify_domain(event, domain):
    from pretix.plugins.stripe.payment import StripeCC
    prov = StripeCC(event)
    account = get_stripe_account_key(prov)

    if RegisteredApplePayDomain.objects.filter(account=account, domain=domain).exists():
        return

    try:
        resp = stripe.ApplePayDomain.create(
            domain_name=domain,
            **prov.api_kwargs
        )
    except stripe.error.StripeError:
        logger.exception('Could not verify domain with Stripe')
    else:
        if resp.livemode:
            RegisteredApplePayDomain.objects.create(
                domain=domain,
                account=account
            )
