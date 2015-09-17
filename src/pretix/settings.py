import configparser
import os
import sys

import django.conf.locale
from django.contrib.messages import constants as messages  # NOQA
from django.utils.crypto import get_random_string
from django.utils.translation import ugettext_lazy as _  # NOQA

config = configparser.ConfigParser()
config.read(['/etc/pretix/pretix.cfg', os.path.expanduser('~/.pretix.cfg'), 'pretix.cfg'],
            encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = config.get('pretix', 'datadir', fallback=os.environ.get('DATA_DIR', 'data'))
LOG_DIR = os.path.join(DATA_DIR, 'logs')
MEDIA_ROOT = os.path.join(DATA_DIR, 'media')

if not os.path.exists(DATA_DIR):
    os.mkdir(DATA_DIR)
if not os.path.exists(LOG_DIR):
    os.mkdir(LOG_DIR)
if not os.path.exists(MEDIA_ROOT):
    os.mkdir(MEDIA_ROOT)

if config.has_option('django', 'secret'):
    SECRET_KEY = config.get('django', 'secret')
else:
    SECRET_FILE = os.path.join(DATA_DIR, '.secret')
    if os.path.exists(SECRET_FILE):
        with open(SECRET_FILE, 'r') as f:
            SECRET_KEY = f.read().strip()
    else:
        chars = 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)'
        SECRET_KEY = get_random_string(50, chars)
        with open(SECRET_FILE, 'w') as f:
            f.write(SECRET_KEY)

# Adjustable settings

debug_fallback = "runserver" in sys.argv
DEBUG = config.getboolean('django', 'debug', fallback=debug_fallback)

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.' + config.get('database', 'backend', fallback='sqlite3'),
        'NAME': config.get('database', 'name', fallback=os.path.join(DATA_DIR, 'db.sqlite3')),
        'USER': config.get('database', 'user', fallback=''),
        'PASSWORD': config.get('database', 'password', fallback=''),
        'HOST': config.get('database', 'host', fallback=''),
        'PORT': config.get('database', 'port', fallback='')
    }
}

STATIC_URL = config.get('urls', 'static', fallback='/static/')

MEDIA_URL = config.get('urls', 'media', fallback='/media/')

PRETIX_INSTANCE_NAME = config.get('pretix', 'instance_name', fallback='pretix.de')

SITE_URL = config.get('pretix', 'url', fallback='http://localhost')

PRETIX_PLUGINS_DEFAULT = config.get('pretix', 'plugins_default',
                                    fallback='pretix.plugins.sendmail,pretix.plugins.statistics')

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

ADMINS = [('Admin', n) for n in config.get('mail', 'admins', fallback='').split(",") if n]

SESSION_COOKIE_SECURE = SESSION_COOKIE_HTTPONLY = config.getboolean(
    'pretix', 'securecookie', fallback=False)
LANGUAGE_COOKIE_DOMAIN = SESSION_COOKIE_DOMAIN = CSRF_COOKIE_DOMAIN = config.get(
    'pretix', 'cookiedomain', fallback=None)

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}

HAS_MEMCACHED = config.has_option('memcached', 'location')
if HAS_MEMCACHED:
    CACHES['default'] = {
        'BACKEND': 'django.core.cache.backends.memcached.PyLibMCCache',
        'LOCATION': config.get('memcached', 'location'),
    }

HAS_REDIS = config.has_option('redis', 'location')
if HAS_REDIS:
    CACHES['redis'] = {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": config.get('redis', 'location'),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }
    if not HAS_MEMCACHED:
        CACHES['default'] = CACHES['redis']
    if config.getboolean('redis', 'sessions', fallback=False):
        SESSION_ENGINE = "django.contrib.sessions.backends.cache"
        SESSION_CACHE_ALIAS = "redis"

HAS_CELERY = config.has_option('celery', 'broker')
if HAS_CELERY:
    BROKER_URL = config.get('celery', 'broker')
    CELERY_RESULT_BACKEND = config.get('celery', 'backend')
    CELERY_SEND_TASK_ERROR_EMAILS = bool(ADMINS)

# Internal settings

STATIC_ROOT = '_static'

SESSION_COOKIE_NAME = 'pretix_session'
LANGUAGE_COOKIE_NAME = 'pretix_language'
CSRF_COOKIE_NAME = 'pretix_csrftoken'

INSTALLED_APPS = (
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
    'pretix.plugins.timerestriction',
    'pretix.plugins.banktransfer',
    'pretix.plugins.stripe',
    'pretix.plugins.paypal',
    'pretix.plugins.ticketoutputpdf',
    'pretix.plugins.sendmail',
    'pretix.plugins.statistics',
    'pretix.plugins.reports',
    'pretix.plugins.pretixdroid',
    'easy_thumbnails',
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

LANGUAGES = (
    ('en', _('English')),
    ('de', _('German')),
    ('de-informal', _('German (informal)')),
)

EXTRA_LANG_INFO = {
    'de-informal': {
        'bidi': False,
        'code': 'de-informal',
        'name': 'German (informal)',
        'name_local': 'Deutsch (Du)'
    },
}

django.conf.locale.LANG_INFO.update(EXTRA_LANG_INFO)


AUTH_USER_MODEL = 'pretixbase.User'
LOGIN_URL = '/login'  # global login does not yet exist
LOGIN_URL_CONTROL = 'control:auth.login'

template_loaders = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
)
if not DEBUG:
    template_loaders = (
        ('django.template.loaders.cached.Loader', template_loaders),
    )

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            os.path.join(DATA_DIR, 'templates'),
            os.path.join(BASE_DIR, 'templates'),
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

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static')
]

if os.path.exists(os.path.join(DATA_DIR, 'static')):
    STATICFILES_DIRS.insert(0, os.path.join(DATA_DIR, 'static'))

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

MESSAGE_TAGS = {
    messages.INFO: 'alert-info',
    messages.ERROR: 'alert-danger',
    messages.WARNING: 'alert-warning',
    messages.SUCCESS: 'alert-success',
}

THUMBNAIL_ALIASES = {
    '': {
        'productlist': {'size': (60, 60), 'crop': True},
    },
}

loglevel = 'DEBUG' if DEBUG else 'INFO'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '%(levelname)s %(asctime)s %(name)s %(module)s %(message)s'
        },
    },
    'filters': {
        'require_admin_enabled': {
            '()': 'pretix.helpers.logs.AdminExistsFilter',
        }
    },
    'handlers': {
        'console': {
            'level': loglevel,
            'class': 'logging.StreamHandler',
            'formatter': 'default'
        },
        'file': {
            'level': loglevel,
            'class': 'logging.FileHandler',
            'filename': os.path.join(LOG_DIR, 'pretix.log'),
            'formatter': 'default'
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
            'filters': ['require_admin_enabled']
        }
    },
    'loggers': {
        '': {
            'handlers': ['file', 'console'],
            'level': loglevel,
            'propagate': True,
        },
        'django.request': {
            'handlers': ['file', 'console', 'mail_admins'],
            'level': loglevel,
            'propagate': True,
        },
        'django.security': {
            'handlers': ['file', 'console', 'mail_admins'],
            'level': loglevel,
            'propagate': True,
        },
        'django.db.backends': {
            'handlers': ['file', 'console'],
            'level': 'INFO',  # Do not output all the queries
            'propagate': True,
        }
    },
}

CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
