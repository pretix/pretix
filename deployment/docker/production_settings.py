from pretix.settings import *

LOGGING['handlers']['mail_admins']['include_html'] = True
STATIC_ROOT = '/static'
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'
