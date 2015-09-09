import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pretix.settings")

from django.conf import settings

if settings.HAS_CELERY:
    from celery import Celery
    app = Celery('pretix')

    app.config_from_object('django.conf:settings')
    app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)
