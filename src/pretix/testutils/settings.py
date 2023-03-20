#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
import atexit
import os
import tempfile

tmpdir = tempfile.TemporaryDirectory()
os.environ.setdefault('DATA_DIR', tmpdir.name)
if os.path.exists('test/sqlite.cfg'):
    os.environ.setdefault('PRETIX_CONFIG_FILE', 'test/sqlite.cfg')

from pretix.settings import *  # NOQA

LANGUAGE_CODE = 'en'
DATA_DIR = tmpdir.name
LOG_DIR = os.path.join(DATA_DIR, 'logs')
MEDIA_ROOT = os.path.join(DATA_DIR, 'media')
SITE_URL = "http://example.com"

atexit.register(tmpdir.cleanup)

EMAIL_BACKEND = EMAIL_CUSTOM_SMTP_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

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
