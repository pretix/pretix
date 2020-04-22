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
SITE_URL = "http://example.com"

atexit.register(tmpdir.cleanup)

EMAIL_BACKEND = 'django.core.mail.outbox'

COMPRESS_ENABLED = COMPRESS_OFFLINE = False
COMPRESS_CACHE_BACKEND = 'testcache'
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'
PRETIX_INSTANCE_NAME = 'pretix.eu'

COMPRESS_PRECOMPILERS_ORIGINAL = COMPRESS_PRECOMPILERS
COMPRESS_PRECOMPILERS = ()
TEMPLATES[0]['OPTIONS']['loaders'] = (
    ('django.template.loaders.cached.Loader', template_loaders),
)

DEBUG = True
DEBUG_PROPAGATE_EXCEPTIONS = True

PRETIX_AUTH_BACKENDS = [
    'pretix.base.auth.NativeAuthBackend',
]

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

# Disable celery
CELERY_ALWAYS_EAGER = True
HAS_CELERY = False
CELERY_BROKER_URL = None
CELERY_RESULT_BACKEND = None
CELERY_TASK_ALWAYS_EAGER = True

# Don't use redis
SESSION_ENGINE = "django.contrib.sessions.backends.db"
HAS_REDIS = False
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}
DATABASE_REPLICA = 'default'

# Don't run migrations


class DisableMigrations(object):

    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


if not os.environ.get("TRAVIS", "") and not os.environ.get("GITHUB_WORKFLOW", ""):
    MIGRATION_MODULES = DisableMigrations()
