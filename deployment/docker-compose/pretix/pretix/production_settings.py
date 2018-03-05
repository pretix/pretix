from pretix.settings import *

LOGGING['handlers']['mail_admins']['include_html'] = True
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'
