import configparser
import os
import sys
from urllib.parse import urlparse

from kombu import Queue
from pycountry import currencies

import django.conf.locale
from django.contrib.messages import constants as messages  # NOQA
from django.utils.crypto import get_random_string
from django.utils.translation import ugettext_lazy as _  # NOQA
from pkg_resources import iter_entry_points
from . import __version__

config = configparser.RawConfigParser()
if 'PRETIX_CONFIG_FILE' in os.environ:
    config.read_file(open(os.environ.get('PRETIX_CONFIG_FILE'), encoding='utf-8'))
else:
    config.read(['/etc/pretix/pretix.cfg', os.path.expanduser('~/.pretix.cfg'), 'pretix.cfg'],
                encoding='utf-8')

CONFIG_FILE = config
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = config.get('pretix', 'datadir', fallback=os.environ.get('DATA_DIR', 'data'))
LOG_DIR = os.path.join(DATA_DIR, 'logs')
MEDIA_ROOT = os.path.join(DATA_DIR, 'media')
PROFILE_DIR = os.path.join(DATA_DIR, 'profiles')

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
            os.chmod(SECRET_FILE, 0o600)
            try:
                os.chown(SECRET_FILE, os.getuid(), os.getgid())
            except AttributeError:
                pass  # os.chown is not available on Windows
            f.write(SECRET_KEY)

# Adjustable settings

debug_fallback = "runserver" in sys.argv
DEBUG = config.getboolean('django', 'debug', fallback=debug_fallback)

db_backend = config.get('database', 'backend', fallback='sqlite3')
DATABASE_IS_GALERA = config.getboolean('database', 'galera', fallback=False)
if DATABASE_IS_GALERA and 'mysql' in db_backend:
    db_options = {
        'init_command': 'SET SESSION wsrep_sync_wait = 1;'
    }
else:
    db_options = {}

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.' + db_backend,
        'NAME': config.get('database', 'name', fallback=os.path.join(DATA_DIR, 'db.sqlite3')),
        'USER': config.get('database', 'user', fallback=''),
        'PASSWORD': config.get('database', 'password', fallback=''),
        'HOST': config.get('database', 'host', fallback=''),
        'PORT': config.get('database', 'port', fallback=''),
        'CONN_MAX_AGE': 0 if db_backend == 'sqlite3' else 120,
        'OPTIONS': db_options
    }
}

STATIC_URL = config.get('urls', 'static', fallback='/static/')

MEDIA_URL = config.get('urls', 'media', fallback='/media/')

PRETIX_INSTANCE_NAME = config.get('pretix', 'instance_name', fallback='pretix.de')
PRETIX_REGISTRATION = config.getboolean('pretix', 'registration', fallback=True)
PRETIX_PASSWORD_RESET = config.getboolean('pretix', 'password_reset', fallback=True)
PRETIX_LONG_SESSIONS = config.getboolean('pretix', 'long_sessions', fallback=True)
PRETIX_ADMIN_AUDIT_COMMENTS = config.getboolean('pretix', 'audit_comments', fallback=False)
PRETIX_SESSION_TIMEOUT_RELATIVE = 3600 * 3
PRETIX_SESSION_TIMEOUT_ABSOLUTE = 3600 * 12

SITE_URL = config.get('pretix', 'url', fallback='http://localhost')
if SITE_URL.endswith('/'):
    SITE_URL = SITE_URL[:-1]

CSRF_TRUSTED_ORIGINS = [urlparse(SITE_URL).hostname]

PRETIX_PLUGINS_DEFAULT = config.get('pretix', 'plugins_default',
                                    fallback='pretix.plugins.sendmail,pretix.plugins.statistics,pretix.plugins.checkinlists')

FETCH_ECB_RATES = config.getboolean('pretix', 'ecb_rates', fallback=True)

DEFAULT_CURRENCY = config.get('pretix', 'currency', fallback='EUR')
CURRENCIES = list(currencies)
CURRENCY_PLACES = {
    # default is 2
    'BIF': 0,
    'CLP': 0,
    'DJF': 0,
    'GNF': 0,
    'JPY': 0,
    'KMF': 0,
    'KRW': 0,
    'MGA': 0,
    'PYG': 0,
    'RWF': 0,
    'VND': 0,
    'VUV': 0,
    'XAF': 0,
    'XOF': 0,
    'XPF': 0,
}

ALLOWED_HOSTS = ['*']

LANGUAGE_CODE = config.get('locale', 'default', fallback='en')
TIME_ZONE = config.get('locale', 'timezone', fallback='UTC')

MAIL_FROM = SERVER_EMAIL = DEFAULT_FROM_EMAIL = config.get(
    'mail', 'from', fallback='pretix@localhost')
EMAIL_HOST = config.get('mail', 'host', fallback='localhost')
EMAIL_PORT = config.getint('mail', 'port', fallback=25)
EMAIL_HOST_USER = config.get('mail', 'user', fallback='')
EMAIL_HOST_PASSWORD = config.get('mail', 'password', fallback='')
EMAIL_USE_TLS = config.getboolean('mail', 'tls', fallback=False)
EMAIL_USE_SSL = config.getboolean('mail', 'ssl', fallback=False)
EMAIL_SUBJECT_PREFIX = '[pretix] '

ADMINS = [('Admin', n) for n in config.get('mail', 'admins', fallback='').split(",") if n]

METRICS_ENABLED = config.getboolean('metrics', 'enabled', fallback=False)
METRICS_USER = config.get('metrics', 'user', fallback="metrics")
METRICS_PASSPHRASE = config.get('metrics', 'passphrase', fallback="")

CACHES = {
    'default': {
        'BACKEND': 'pretix.helpers.cache.CustomDummyCache',
    }
}
REAL_CACHE_USED = False
SESSION_ENGINE = None

HAS_MEMCACHED = config.has_option('memcached', 'location')
if HAS_MEMCACHED:
    REAL_CACHE_USED = True
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
    CACHES['redis_sessions'] = {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": config.get('redis', 'location'),
        "TIMEOUT": 3600 * 24 * 30,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }
    if not HAS_MEMCACHED:
        CACHES['default'] = CACHES['redis']
        REAL_CACHE_USED = True
    if config.getboolean('redis', 'sessions', fallback=False):
        SESSION_ENGINE = "django.contrib.sessions.backends.cache"
        SESSION_CACHE_ALIAS = "redis_sessions"

if not SESSION_ENGINE:
    if REAL_CACHE_USED:
        SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
    else:
        SESSION_ENGINE = "django.contrib.sessions.backends.db"

HAS_CELERY = config.has_option('celery', 'broker')
if HAS_CELERY:
    CELERY_BROKER_URL = config.get('celery', 'broker')
    CELERY_RESULT_BACKEND = config.get('celery', 'backend')
else:
    CELERY_TASK_ALWAYS_EAGER = True

SESSION_COOKIE_DOMAIN = config.get('pretix', 'cookie_domain', fallback=None)

ENTROPY = {
    'order_code': config.getint('entropy', 'order_code', fallback=5),
    'ticket_secret': config.getint('entropy', 'ticket_secret', fallback=32),
    'voucher_code': config.getint('entropy', 'voucher_code', fallback=16),
}

# Internal settings
PRETIX_EMAIL_NONE_VALUE = 'none@well-known.pretix.eu'

STATIC_ROOT = os.path.join(os.path.dirname(__file__), 'static.dist')

SESSION_COOKIE_NAME = 'pretix_session'
LANGUAGE_COOKIE_NAME = 'pretix_language'
CSRF_COOKIE_NAME = 'pretix_csrftoken'
SESSION_COOKIE_HTTPONLY = True

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'pretix.base',
    'pretix.control',
    'pretix.presale',
    'pretix.multidomain',
    'pretix.api',
    'pretix.helpers',
    'rest_framework',
    'django_filters',
    'compressor',
    'bootstrap3',
    'djangoformsetjs',
    'pretix.plugins.banktransfer',
    'pretix.plugins.stripe',
    'pretix.plugins.paypal',
    'pretix.plugins.ticketoutputpdf',
    'pretix.plugins.sendmail',
    'pretix.plugins.statistics',
    'pretix.plugins.reports',
    'pretix.plugins.checkinlists',
    'pretix.plugins.pretixdroid',
    'django_markup',
    'django_otp',
    'django_otp.plugins.otp_totp',
    'django_otp.plugins.otp_static',
    'statici18n',
    'django_countries',
    'hijack',
    'compat',
]

try:
    import django_extensions  # noqa
    INSTALLED_APPS.append('django_extensions')
except ImportError:
    pass

PLUGINS = []
for entry_point in iter_entry_points(group='pretix.plugin', name=None):
    PLUGINS.append(entry_point.module_name)
    INSTALLED_APPS.append(entry_point.module_name)

HIJACK_AUTHORIZE_STAFF = True


REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'pretix.api.auth.permission.EventPermission',
    ],
    'DEFAULT_VERSIONING_CLASS': 'rest_framework.versioning.NamespaceVersioning',
    'PAGE_SIZE': 50,
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'pretix.api.auth.token.TeamTokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
    'EXCEPTION_HANDLER': 'pretix.api.exception.custom_exception_handler',
    'UNICODE_JSON': False
}


CORE_MODULES = {
    "pretix.base",
    "pretix.presale",
    "pretix.control",
    "pretix.plugins.checkinlists",
}

MIDDLEWARE = [
    'django.middleware.common.CommonMiddleware',
    'pretix.multidomain.middlewares.MultiDomainMiddleware',
    'pretix.multidomain.middlewares.SessionMiddleware',
    'pretix.multidomain.middlewares.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'pretix.control.middleware.PermissionMiddleware',
    'pretix.control.middleware.AuditLogMiddleware',
    'pretix.base.middleware.LocaleMiddleware',
    'pretix.base.middleware.SecurityMiddleware',
    'pretix.presale.middleware.EventMiddleware',
]

try:
    import debug_toolbar  # noqa
    if DEBUG:
        INSTALLED_APPS.append('debug_toolbar.apps.DebugToolbarConfig')
        MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')
except ImportError:
    pass


if METRICS_ENABLED:
    MIDDLEWARE.insert(MIDDLEWARE.index('pretix.multidomain.middlewares.MultiDomainMiddleware') + 1,
                      'pretix.helpers.metrics.middleware.MetricsMiddleware')


PROFILING_RATE = config.getfloat('django', 'profile', fallback=0)  # Percentage of requests to profile
if PROFILING_RATE > 0:
    if not os.path.exists(PROFILE_DIR):
        os.mkdir(PROFILE_DIR)
    MIDDLEWARE.insert(0, 'pretix.helpers.profile.middleware.CProfileMiddleware')


# Security settings
X_FRAME_OPTIONS = 'DENY'

# URL settings
ROOT_URLCONF = 'pretix.multidomain.maindomain_urlconf'

WSGI_APPLICATION = 'pretix.wsgi.application'

USE_I18N = True
USE_L10N = True
USE_TZ = True

LOCALE_PATHS = (
    os.path.join(os.path.dirname(__file__), 'locale'),
)

FORMAT_MODULE_PATH = [
    'pretix.helpers.formats',
]

ALL_LANGUAGES = [
    ('en', _('English')),
    ('de', _('German')),
    ('de-informal', _('German (informal)')),
    ('nl', _('Dutch')),
    ('da', _('Danish')),
    ('pt-br', _('Portuguese (Brazil)')),
]
LANGUAGES_OFFICIAL = {
    'en', 'de', 'de-informal'
}
LANGUAGES_INCUBATING = {
    'nl', 'pt-br', 'da'
}

if DEBUG:
    LANGUAGES = ALL_LANGUAGES
else:
    LANGUAGES = [(k, v) for k, v in ALL_LANGUAGES if k not in LANGUAGES_INCUBATING]


EXTRA_LANG_INFO = {
    'de-informal': {
        'bidi': False,
        'code': 'de-informal',
        'name': 'German (informal)',
        'name_local': 'Deutsch'
    },
}

django.conf.locale.LANG_INFO.update(EXTRA_LANG_INFO)


AUTH_USER_MODEL = 'pretixbase.User'
LOGIN_URL = '/login'  # global login does not yet exist
LOGIN_URL_CONTROL = 'control:auth.login'
CSRF_FAILURE_VIEW = 'pretix.base.views.errors.csrf_failure'

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
    os.path.join(BASE_DIR, 'pretix/static')
] if os.path.exists(os.path.join(BASE_DIR, 'pretix/static')) else []

STATICI18N_ROOT = os.path.join(BASE_DIR, "pretix/static")

STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'

# if os.path.exists(os.path.join(DATA_DIR, 'static')):
#     STATICFILES_DIRS.insert(0, os.path.join(DATA_DIR, 'static'))

COMPRESS_PRECOMPILERS = (
    ('text/x-scss', 'django_libsass.SassCompiler'),
)

COMPRESS_ENABLED = COMPRESS_OFFLINE = not debug_fallback

COMPRESS_CSS_FILTERS = (
    # CssAbsoluteFilter is incredibly slow, especially when dealing with our _flags.scss
    # However, we don't need it if we consequently use the static() function in Sass
    # 'compressor.filters.css_default.CssAbsoluteFilter',
    'compressor.filters.cssmin.CSSCompressorFilter',
)

# Debug toolbar
DEBUG_TOOLBAR_PATCH_SETTINGS = False


DEBUG_TOOLBAR_CONFIG = {
    'JQUERY_URL': '',
}

INTERNAL_IPS = ('127.0.0.1', '::1')

MESSAGE_TAGS = {
    messages.INFO: 'alert-info',
    messages.ERROR: 'alert-danger',
    messages.WARNING: 'alert-warning',
    messages.SUCCESS: 'alert-success',
}
MESSAGE_STORAGE = 'django.contrib.messages.storage.session.SessionStorage'

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
        'csp_file': {
            'level': loglevel,
            'class': 'logging.FileHandler',
            'filename': os.path.join(LOG_DIR, 'csp.log'),
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
        'pretix.security.csp': {
            'handlers': ['csp_file'],
            'level': loglevel,
            'propagate': False,
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

if config.has_option('sentry', 'dsn'):
    INSTALLED_APPS += [
        'pretix.sentry.App',
    ]
    RAVEN_CONFIG = {
        'dsn': config.get('sentry', 'dsn'),
        'transport': 'raven.transport.threaded_requests.ThreadedRequestsHTTPTransport',
        'release': __version__,
        'environment': SITE_URL,
    }

CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TASK_DEFAULT_QUEUE = 'default'
CELERY_TASK_QUEUES = (
    Queue('default', routing_key='default.#'),
    Queue('checkout', routing_key='checkout.#'),
    Queue('mail', routing_key='mail.#'),
    Queue('background', routing_key='background.#'),
)
CELERY_TASK_ROUTES = ([
    ('pretix.base.services.cart.*', {'queue': 'checkout'}),
    ('pretix.base.services.orders.*', {'queue': 'checkout'}),
    ('pretix.base.services.mail.*', {'queue': 'mail'}),
    ('pretix.base.services.style.*', {'queue': 'background'}),
    ('pretix.base.services.update_check.*', {'queue': 'background'}),
    ('pretix.base.services.quotas.*', {'queue': 'background'}),
    ('pretix.base.services.waitinglist.*', {'queue': 'background'}),
    ('pretix.plugins.banktransfer.*', {'queue': 'background'}),
],)

BOOTSTRAP3 = {
    'success_css_class': '',
    'field_renderers': {
        'default': 'bootstrap3.renderers.FieldRenderer',
        'inline': 'bootstrap3.renderers.InlineFieldRenderer',
        'control': 'pretix.control.forms.renderers.ControlFieldRenderer',
    },
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]
