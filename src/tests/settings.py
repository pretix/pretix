import os

from pretix.settings import *  # NOQA

TEST_DIR = os.path.dirname(__file__)

TEMPLATES[0]['DIRS'].append(os.path.join(TEST_DIR, 'templates'))  # NOQA

INSTALLED_APPS.append('tests.testdummy')  # NOQA

MEDIA_ROOT = os.path.join(TEST_DIR, 'media')

EMAIL_BACKEND = 'django.core.mail.outbox'

COMPRESS_ENABLED = COMPRESS_OFFLINE = False
