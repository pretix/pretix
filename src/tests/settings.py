from pretix.settings import *  # NOQA

TEST_DIR = os.path.dirname(__file__)

TEMPLATES[0]['DIRS'].append(os.path.join(TEST_DIR, 'templates'))

INSTALLED_APPS = INSTALLED_APPS + (
    'tests.testdummy',
)

MEDIA_ROOT = os.path.join(TEST_DIR, 'media')
