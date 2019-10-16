import os
from pretix.testutils.settings import *  # NOQA


TEST_DIR = os.path.dirname(__file__)

TEMPLATES[0]['DIRS'].append(os.path.join(TEST_DIR, 'templates'))  # NOQA

INSTALLED_APPS.append('tests.testdummy')  # NOQA

PRETIX_AUTH_BACKENDS = [
    'pretix.base.auth.NativeAuthBackend',
    'tests.testdummy.auth.TestFormAuthBackend',
    'tests.testdummy.auth.TestRequestAuthBackend',
]

for a in PLUGINS:
    INSTALLED_APPS.remove(a)
