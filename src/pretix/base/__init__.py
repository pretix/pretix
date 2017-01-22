from django.apps import AppConfig


class PretixBaseConfig(AppConfig):
    name = 'pretix.base'
    label = 'pretixbase'

    def ready(self):
        from . import exporter  # NOQA
        from . import payment  # NOQA
        from . import exporters  # NOQA
        from .services import export, mail, tickets, cart, orders, cleanup  # NOQA

        try:
            from .celery_app import app as celery_app  # NOQA
        except ImportError:
            pass


default_app_config = 'pretix.base.PretixBaseConfig'
try:
    import pretix.celery_app as celery  # NOQA
except ImportError:
    pass
