import configparser
import os
from django.utils.crypto import get_random_string

config = configparser.ConfigParser()
config.read(['/etc/pretix/pretix.cfg', os.path.expanduser('~/.pretix.cfg'), 'pretix.cfg'],
            encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

if config.has_option('django', 'secret'):
    SECRET_KEY = config.get('django', 'secret')
else:
    SECRET_FILE = os.path.join(BASE_DIR, '.secret')
    if os.path.exists(SECRET_FILE):
        with open(SECRET_FILE, 'r') as f:
            SECRET_KEY = f.read().strip()
    else:
        chars = 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)'
        SECRET_KEY = get_random_string(50, chars)
        with open(SECRET_FILE, 'w') as f:
            f.write(SECRET_KEY)

# Adjustable settings

DEBUG = TEMPLATE_DEBUG = config.getboolean('django', 'debug', fallback=False)

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.' + config.get('database', 'backend', fallback='sqlite3'),
        'NAME': config.get('database', 'name', fallback=os.path.join(BASE_DIR, 'db.sqlite3')),
        'USER': config.get('database', 'user', fallback=''),
        'PASSWORD': config.get('database', 'password', fallback=''),
        'HOST': config.get('database', 'host', fallback=''),
        'PORT': config.get('database', 'port', fallback='')
    }
}

STATIC_URL = config.get('static', 'url', fallback='/static/')
STATIC_ROOT = config.get('static', 'root', fallback='_static')

MEDIA_URL = config.get('media', 'url', fallback=os.environ.get('MEDIA_ROOT', '/media/'))
MEDIA_ROOT = config.get('media', 'root', fallback='media')

PRETIX_INSTANCE_NAME = config.get('pretix', 'instance_name', fallback='pretix.de')
PRETIX_GLOBAL_REGISTRATION = config.getboolean('pretix', 'global_registration', fallback=True)

SITE_URL = config.get('pretix', 'url', fallback='http://localhost')

DEFAULT_CURRENCY = config.get('pretix', 'currency', fallback='EUR')

ALLOWED_HOSTS = config.get('django', 'hosts', fallback='localhost').split(',')

LANGUAGE_CODE = config.get('locale', 'default', fallback='en')
TIME_ZONE = config.get('locale', 'timezone', fallback='UTC')

MAIL_FROM = SERVER_EMAIL = DEFAULT_FROM_EMAIL = config.get(
    'mail', 'from', fallback='pretix@localhost')
EMAIL_HOST = config.get('mail', 'host', fallback='localhost')
EMAIL_PORT = config.getint('mail', 'port', fallback=25)
EMAIL_HOST_USER = config.get('mail', 'user', fallback='')
EMAIL_HOST_PASSWORD = config.get('mail', 'password', fallback='')

SESSION_COOKIE_SECURE = SESSION_COOKIE_HTTPONLY = config.getboolean(
    'pretix', 'securecookie', fallback=False)
LANGUAGE_COOKIE_DOMAIN = SESSION_COOKIE_DOMAIN = CSRF_COOKIE_DOMAIN = config.get(
    'pretix', 'cookiedomain', fallback=None)

# Internal settings

SESSION_COOKIE_NAME = 'pretix_session'
LANGUAGE_COOKIE_NAME = 'pretix_language'
CSRF_COOKIE_NAME = 'pretix_csrftoken'

INSTALLED_APPS = (
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'pretix.base',
    'pretix.control',
    'pretix.presale',
    'compressor',
    'bootstrap3',
    'debug_toolbar.apps.DebugToolbarConfig',
    'djangoformsetjs',
    'pretix.plugins.testdummy',
    'pretix.plugins.timerestriction',
    'pretix.plugins.banktransfer',
    'pretix.plugins.stripe',
    'pretix.plugins.paypal',
    'pretix.plugins.ticketoutputpdf',
)

MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'pretix.control.middleware.PermissionMiddleware',
    'pretix.presale.middleware.EventMiddleware',
    'pretix.base.middleware.LocaleMiddleware',
)

ROOT_URLCONF = 'pretix.urls'

WSGI_APPLICATION = 'pretix.wsgi.application'

USE_I18N = True
USE_L10N = True
USE_TZ = True

LOCALE_PATHS = (
    'locale',
)

from django.utils.translation import ugettext_lazy as _  # NOQA
LANGUAGES = (
    ('en', _('English')),
    ('de', _('German')),
)

AUTH_USER_MODEL = 'pretixbase.User'
LOGIN_URL = '/login'  # global login does not yet exist
LOGIN_URL_CONTROL = 'control:auth.login'

template_loaders = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
)
if DEBUG:
    template_loaders = (
        ('django.template.loaders.cached.Loader', template_loaders),
    )

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            os.path.join(BASE_DIR, 'templates')
        ],
        'OPTIONS': {
            'context_processors': [
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.debug',
                'django.template.context_processors.i18n',
                'django.template.context_processors.media',
                "django.template.context_processors.request",
                'django.template.context_processors.static',
                'django.template.context_processors.tz',
                'django.contrib.messages.context_processors.messages',
                'pretix.control.context.contextprocessor',
                'pretix.presale.context.contextprocessor',
            ],
            'loaders': template_loaders
        },
    },
]

STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    'compressor.finders.CompressorFinder',
)

COMPRESS_PRECOMPILERS = (
    ('text/less', 'pretix.helpers.lessabsolutefilter.LessFilter'),
)

COMPRESS_ENABLED = COMPRESS_OFFLINE = not DEBUG

COMPRESS_CSS_FILTERS = (
    'compressor.filters.css_default.CssAbsoluteFilter',
    'compressor.filters.cssmin.CSSMinFilter',
)

# Debug toolbar
DEBUG_TOOLBAR_PATCH_SETTINGS = False
DEBUG_TOOLBAR_CONFIG = {
    'JQUERY_URL': ''
}

INTERNAL_IPS = ('127.0.0.1', '::1')

from django.contrib.messages import constants as messages  # NOQA
MESSAGE_TAGS = {
    messages.INFO: 'alert-info',
    messages.ERROR: 'alert-danger',
    messages.WARNING: 'alert-warning',
    messages.SUCCESS: 'alert-success',
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '%(levelname)s %(asctime)s %(module)s %(message)s'
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'default'
        },

    },
    'loggers': {
        '': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': True,
        },
    },
}
