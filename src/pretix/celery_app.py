import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pretix.settings")

from django.conf import settings

app = Celery('pretix')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)


if hasattr(settings, 'RAVEN_CONFIG'):
    # Celery signal registration
    from raven.contrib.celery import register_signal
    from raven.contrib.django.models import client
    register_signal(client, ignore_expected=True)
