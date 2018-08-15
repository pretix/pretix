import stripe
from django.core.management.base import BaseCommand

from pretix.base.models import Event
from pretix.base.settings import GlobalSettingsObject


class Command(BaseCommand):
    help = "Detect country for Stripe Connect accounts connected with pretix 2.0 (required for payment request buttons)"

    def handle(self, *args, **options):
        cache = {}
        gs = GlobalSettingsObject()
        api_key = gs.settings.payment_stripe_connect_secret_key or gs.settings.payment_stripe_connect_test_secret_key
        if not api_key:
            self.stderr.write(self.style.ERROR("Stripe Connect is not set up!"))
            return

        for e in Event.objects.filter(plugins__icontains="pretix.plugins.stripe"):
            uid = e.settings.payment_stripe_connect_user_id
            if uid and not e.settings.payment_stripe_merchant_country:
                if uid in cache:
                    e.settings.payment_stripe_merchant_country = cache[uid]
                else:
                    try:
                        account = stripe.Account.retrieve(
                            uid,
                            api_key=api_key
                        )
                    except Exception as e:
                        print(e)
                    else:
                        e.settings.payment_stripe_merchant_country = cache[uid] = account.get('country')
