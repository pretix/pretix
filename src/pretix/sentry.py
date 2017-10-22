from threading import Lock

from raven.contrib.celery import SentryCeleryHandler
from raven.contrib.django.apps import RavenConfig
from raven.contrib.django.models import (
    SentryDjangoHandler, client, get_client, install_middleware,
    register_serializers,
)

_setup_lock = Lock()

_initialized = False


class CustomSentryDjangoHandler(SentryDjangoHandler):
    def install_celery(self):
        self.celery_handler = SentryCeleryHandler(client, ignore_expected=True).install()


def initialize():
    global _initialized

    with _setup_lock:
        if _initialized:
            return

        _initialized = True

        try:
            register_serializers()
            install_middleware(
                'raven.contrib.django.middleware.SentryMiddleware',
                (
                    'raven.contrib.django.middleware.SentryMiddleware',
                    'raven.contrib.django.middleware.SentryLogMiddleware'))
            install_middleware(
                'raven.contrib.django.middleware.DjangoRestFrameworkCompatMiddleware')

            handler = CustomSentryDjangoHandler()
            handler.install()

            # instantiate client so hooks get registered
            get_client()  # NOQA
        except Exception:
            _initialized = False


class App(RavenConfig):
    def ready(self):
        initialize()
