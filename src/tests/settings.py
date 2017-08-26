import os
from pretix.testutils.settings import *  # NOQA


TEST_DIR = os.path.dirname(__file__)

TEMPLATES[0]['DIRS'].append(os.path.join(TEST_DIR, 'templates'))  # NOQA

INSTALLED_APPS.append('tests.testdummy')  # NOQA

for a in PLUGINS:
    INSTALLED_APPS.remove(a)