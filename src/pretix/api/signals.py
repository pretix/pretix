from datetime import timedelta

from django.dispatch import Signal, receiver
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.api.models import ApiCall, WebHookCall
from pretix.base.signals import periodic_task

register_webhook_events = Signal(
    providing_args=[]
)
"""
This signal is sent out to get all known webhook events. Receivers should return an
instance of a subclass of pretix.api.webhooks.WebhookEvent or a list of such
instances.
"""


@receiver(periodic_task)
@scopes_disabled()
def cleanup_webhook_logs(sender, **kwargs):
    WebHookCall.objects.filter(datetime__lte=now() - timedelta(days=30)).delete()


@receiver(periodic_task)
@scopes_disabled()
def cleanup_api_logs(sender, **kwargs):
    ApiCall.objects.filter(created__lte=now() - timedelta(hours=24)).delete()
