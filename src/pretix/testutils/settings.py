import atexit
import os
import tempfile

tmpdir = tempfile.TemporaryDirectory()
os.environ.setdefault('DATA_DIR', tmpdir.name)
if os.path.exists('test/sqlite.cfg'):
    os.environ.setdefault('PRETIX_CONFIG_FILE', 'test/sqlite.cfg')

from pretix.settings import *  # NOQA

DATA_DIR = tmpdir.name
LOG_DIR = os.path.join(DATA_DIR, 'logs')
MEDIA_ROOT = os.path.join(DATA_DIR, 'media')

atexit.register(tmpdir.cleanup)

EMAIL_BACKEND = 'django.core.mail.outbox'

COMPRESS_ENABLED = COMPRESS_OFFLINE = False
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'
PRETIX_INSTANCE_NAME = 'pretix.eu'

DEBUG = True
DEBUG_PROPAGATE_EXCEPTIONS = True

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

# Disable celery
CELERY_ALWAYS_EAGER = True
HAS_CELERY = False

# Don't use redis
SESSION_ENGINE = "django.contrib.sessions.backends.db"
HAS_REDIS = False
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# Don't run migrations


class DisableMigrations(object):

    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


if not os.environ.get("TRAVIS", ""):
    MIGRATION_MODULES = DisableMigrations()
