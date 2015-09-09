__version__ = "0.0.0"

try:
    from .celery import app as celery_app
except ImportError:
    pass
