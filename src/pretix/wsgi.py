"""
WSGI config for pretix project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/dev/howto/deployment/wsgi/
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pretix.settings")

from django.core.wsgi import get_wsgi_application  # NOQA

try:
    from dj_static import Cling, MediaCling
    application = Cling(MediaCling(get_wsgi_application()))
except ImportError:
    application = get_wsgi_application()
