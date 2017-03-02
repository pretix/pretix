import atexit
import os
import tempfile

tmpdir = tempfile.TemporaryDirectory()
os.environ.setdefault('DATA_DIR', tmpdir.name)
os.environ.setdefault('PRETIX_CONFIG_FILE', 'test/sqlite.cfg')

from pretix.settings import *  # NOQA

DATA_DIR = tmpdir.name
LOG_DIR = os.path.join(DATA_DIR, 'logs')
MEDIA_ROOT = os.path.join(DATA_DIR, 'media')

atexit.register(tmpdir.cleanup)

EMAIL_BACKEND = 'django.core.mail.outbox'

COMPRESS_ENABLED = COMPRESS_OFFLINE = False

DEBUG = True

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
