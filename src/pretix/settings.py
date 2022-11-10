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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: FlaviaBastos, Jason Estibeiro, Jonas Große Sundrup,
# Laura Klünder, Matthew Emerson, Nils Schneider, Tim Freund, Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import configparser
import logging
import os
import sys
from urllib.parse import urlparse
from json import loads

import django.conf.locale
from django.utils.crypto import get_random_string
from kombu import Queue
from pkg_resources import iter_entry_points
from pycountry import currencies

from . import __version__
from .helpers.config import EnvOrParserConfig


from django.contrib.messages import constants as messages  # NOQA
from django.utils.translation import gettext_lazy as _  # NOQA

_config = configparser.RawConfigParser()
if 'PRETIX_CONFIG_FILE' in os.environ:
    _config.read_file(open(os.environ.get('PRETIX_CONFIG_FILE'), encoding='utf-8'))
else:
    _config.read(['/etc/pretix/pretix.cfg', os.path.expanduser('~/.pretix.cfg'), 'pretix.cfg'],
                 encoding='utf-8')
config = EnvOrParserConfig(_config)

CONFIG_FILE = config
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = config.get('pretix', 'datadir', fallback=os.environ.get('DATA_DIR', 'data'))
LOG_DIR = os.path.join(DATA_DIR, 'logs')
MEDIA_ROOT = os.path.join(DATA_DIR, 'media')
PROFILE_DIR = os.path.join(DATA_DIR, 'profiles')
CACHE_DIR = os.path.join(DATA_DIR, 'cache')

if not os.path.exists(DATA_DIR):
    os.mkdir(DATA_DIR)
if not os.path.exists(LOG_DIR):
    os.mkdir(LOG_DIR)
if not os.path.exists(MEDIA_ROOT):
    os.mkdir(MEDIA_ROOT)
if not os.path.exists(CACHE_DIR):
    os.mkdir(CACHE_DIR)

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
LOG_CSP = config.getboolean('pretix', 'csp_log', fallback=False)
CSP_ADDITIONAL_HEADER = config.get('pretix', 'csp_additional_header', fallback='')

PDFTK = config.get('tools', 'pdftk', fallback=None)

PRETIX_AUTH_BACKENDS = config.get('pretix', 'auth_backends', fallback='pretix.base.auth.NativeAuthBackend').split(',')

db_backend = config.get('database', 'backend', fallback='sqlite3')
if db_backend == 'postgresql_psycopg2':
    db_backend = 'postgresql'
DATABASE_IS_GALERA = config.getboolean('database', 'galera', fallback=False)
if DATABASE_IS_GALERA and 'mysql' in db_backend:
    db_options = {
        'init_command': 'SET SESSION wsrep_sync_wait = 1;'
    }
else:
    db_options = {}

if 'mysql' in db_backend:
    db_options['charset'] = 'utf8mb4'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.' + db_backend,
        'NAME': config.get('database', 'name', fallback=os.path.join(DATA_DIR, 'db.sqlite3')),
        'USER': config.get('database', 'user', fallback=''),
        'PASSWORD': config.get('database', 'password', fallback=''),
        'HOST': config.get('database', 'host', fallback=''),
        'PORT': config.get('database', 'port', fallback=''),
        'CONN_MAX_AGE': 0 if db_backend == 'sqlite3' else 120,
        'OPTIONS': db_options,
        'TEST': {
            'CHARSET': 'utf8mb4',
            'COLLATION': 'utf8mb4_unicode_ci',
        } if 'mysql' in db_backend else {}
    }
}
DATABASE_REPLICA = 'default'
if config.has_section('replica'):
    DATABASE_REPLICA = 'replica'
    DATABASES['replica'] = {
        'ENGINE': 'django.db.backends.' + db_backend,
        'NAME': config.get('replica', 'name', fallback=DATABASES['default']['NAME']),
        'USER': config.get('replica', 'user', fallback=DATABASES['default']['USER']),
        'PASSWORD': config.get('replica', 'password', fallback=DATABASES['default']['PASSWORD']),
        'HOST': config.get('replica', 'host', fallback=DATABASES['default']['HOST']),
        'PORT': config.get('replica', 'port', fallback=DATABASES['default']['PORT']),
        'CONN_MAX_AGE': 0 if db_backend == 'sqlite3' else 120,
        'OPTIONS': db_options,
        'TEST': {
            'CHARSET': 'utf8mb4',
            'COLLATION': 'utf8mb4_unicode_ci',
        } if 'mysql' in db_backend else {}
    }
    DATABASE_ROUTERS = ['pretix.helpers.database.ReplicaRouter']

STATIC_URL = config.get('urls', 'static', fallback='/static/')

MEDIA_URL = config.get('urls', 'media', fallback='/media/')

PRETIX_INSTANCE_NAME = config.get('pretix', 'instance_name', fallback='pretix.de')
PRETIX_REGISTRATION = config.getboolean('pretix', 'registration', fallback=True)
PRETIX_PASSWORD_RESET = config.getboolean('pretix', 'password_reset', fallback=True)
PRETIX_LONG_SESSIONS = config.getboolean('pretix', 'long_sessions', fallback=True)
PRETIX_ADMIN_AUDIT_COMMENTS = config.getboolean('pretix', 'audit_comments', fallback=False)
PRETIX_OBLIGATORY_2FA = config.getboolean('pretix', 'obligatory_2fa', fallback=False)
PRETIX_SESSION_TIMEOUT_RELATIVE = 3600 * 3
PRETIX_SESSION_TIMEOUT_ABSOLUTE = 3600 * 12
PRETIX_PRIMARY_COLOR = '#8E44B3'

SITE_URL = config.get('pretix', 'url', fallback='http://localhost:8000')
if SITE_URL.endswith('/'):
    SITE_URL = SITE_URL[:-1]

CSRF_TRUSTED_ORIGINS = [urlparse(SITE_URL).hostname]

TRUST_X_FORWARDED_FOR = config.get('pretix', 'trust_x_forwarded_for', fallback=False)

REQUEST_ID_HEADER = config.get('pretix', 'request_id_header', fallback=False)

if config.get('pretix', 'trust_x_forwarded_proto', fallback=False):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

PRETIX_PLUGINS_DEFAULT = config.get('pretix', 'plugins_default',
                                    fallback='pretix.plugins.sendmail,pretix.plugins.statistics,pretix.plugins.checkinlists,pretix.plugins.autocheckin')
PRETIX_PLUGINS_EXCLUDE = config.get('pretix', 'plugins_exclude', fallback='').split(',')
PRETIX_PLUGINS_SHOW_META = config.getboolean('pretix', 'plugins_show_meta', fallback=True)

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

MAIL_FROM = SERVER_EMAIL = DEFAULT_FROM_EMAIL = config.get('mail', 'from', fallback='pretix@localhost')
MAIL_FROM_NOTIFICATIONS = config.get('mail', 'from_notifications', fallback=MAIL_FROM)
MAIL_FROM_ORGANIZERS = config.get('mail', 'from_organizers', fallback=MAIL_FROM)
MAIL_CUSTOM_SENDER_VERIFICATION_REQUIRED = config.getboolean('mail', 'custom_sender_verification_required', fallback=True)
MAIL_CUSTOM_SENDER_SPF_STRING = config.get('mail', 'custom_sender_spf_string', fallback='')
MAIL_CUSTOM_SMTP_ALLOW_PRIVATE_NETWORKS = config.getboolean('mail', 'custom_smtp_allow_private_networks', fallback=DEBUG)
EMAIL_HOST = config.get('mail', 'host', fallback='localhost')
EMAIL_PORT = config.getint('mail', 'port', fallback=25)
EMAIL_HOST_USER = config.get('mail', 'user', fallback='')
EMAIL_HOST_PASSWORD = config.get('mail', 'password', fallback='')
EMAIL_USE_TLS = config.getboolean('mail', 'tls', fallback=False)
EMAIL_USE_SSL = config.getboolean('mail', 'ssl', fallback=False)
EMAIL_SUBJECT_PREFIX = '[pretix] '
EMAIL_BACKEND = EMAIL_CUSTOM_SMTP_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

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

# pretix includes caching options for some special situations where full HTML responses are cached. This might be
# stressful for some cache setups so it is enabled by default and currently can't be enabled through pretix.cfg
CACHE_LARGE_VALUES_ALLOWED = False
CACHE_LARGE_VALUES_ALIAS = 'default'

HAS_MEMCACHED = config.has_option('memcached', 'location')
if HAS_MEMCACHED:
    REAL_CACHE_USED = True
    CACHES['default'] = {
        'BACKEND': 'django.core.cache.backends.memcached.PyLibMCCache',
        'LOCATION': config.get('memcached', 'location'),
    }

HAS_REDIS = config.has_option('redis', 'location')
USE_REDIS_SENTINEL = config.has_option('redis', 'sentinels')
HAS_REDIS_PASSWORD = config.has_option('redis', 'password')
if HAS_REDIS:
    OPTIONS = {
        "CLIENT_CLASS": "django_redis.client.DefaultClient",
        "REDIS_CLIENT_KWARGS": {"health_check_interval": 30}
    }

    if USE_REDIS_SENTINEL:
        DJANGO_REDIS_CONNECTION_FACTORY = "django_redis.pool.SentinelConnectionFactory"
        OPTIONS["CLIENT_CLASS"] = "django_redis.client.SentinelClient"
        OPTIONS["CONNECTION_POOL_CLASS"] = "redis.sentinel.SentinelConnectionPool"
        # See https://github.com/jazzband/django-redis/issues/540
        OPTIONS["SENTINEL_KWARGS"] = {"socket_timeout": 1}
        OPTIONS["SENTINELS"] = [tuple(sentinel) for sentinel in loads(config.get('redis', 'sentinels'))]

    if HAS_REDIS_PASSWORD:
        OPTIONS["PASSWORD"] = config.get('redis', 'password')

    CACHES['redis'] = {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": config.get('redis', 'location'),
        "OPTIONS": OPTIONS
    }
    CACHES['redis_sessions'] = {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": config.get('redis', 'location'),
        "TIMEOUT": 3600 * 24 * 30,
        "OPTIONS": OPTIONS
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
HAS_CELERY_BROKER_TRANSPORT_OPTS = config.has_option('celery', 'broker_transport_options')
HAS_CELERY_BACKEND_TRANSPORT_OPTS = config.has_option('celery', 'backend_transport_options')
if HAS_CELERY:
    CELERY_BROKER_URL = config.get('celery', 'broker')
    CELERY_RESULT_BACKEND = config.get('celery', 'backend')
    if HAS_CELERY_BROKER_TRANSPORT_OPTS:
        CELERY_BROKER_TRANSPORT_OPTIONS = loads(config.get('celery', 'broker_transport_options'))
    if HAS_CELERY_BACKEND_TRANSPORT_OPTS:
        CELERY_RESULT_BACKEND_TRANSPORT_OPTIONS = loads(config.get('celery', 'backend_transport_options'))
else:
    CELERY_TASK_ALWAYS_EAGER = True

SESSION_COOKIE_DOMAIN = config.get('pretix', 'cookie_domain', fallback=None)

CACHE_TICKETS_HOURS = config.getint('cache', 'tickets', fallback=24 * 3)

ENTROPY = {
    'order_code': config.getint('entropy', 'order_code', fallback=5),
    'customer_identifier': config.getint('entropy', 'customer_identifier', fallback=7),
    'ticket_secret': config.getint('entropy', 'ticket_secret', fallback=32),
    'voucher_code': config.getint('entropy', 'voucher_code', fallback=16),
    'giftcard_secret': config.getint('entropy', 'giftcard_secret', fallback=12),
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
    'django.contrib.humanize',
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
    'pretix.plugins.paypal2',
    'pretix.plugins.ticketoutputpdf',
    'pretix.plugins.sendmail',
    'pretix.plugins.statistics',
    'pretix.plugins.reports',
    'pretix.plugins.checkinlists',
    'pretix.plugins.pretixdroid',
    'pretix.plugins.badges',
    'pretix.plugins.manualpayment',
    'pretix.plugins.returnurl',
    'pretix.plugins.webcheckin',
    'django_markup',
    'django_otp',
    'django_otp.plugins.otp_totp',
    'django_otp.plugins.otp_static',
    'statici18n',
    'django_countries',
    'hijack',
    'oauth2_provider',
    'phonenumber_field'
]

if db_backend == 'postgresql':
    # ALlow plugins to use django.contrib.postgres
    INSTALLED_APPS.insert(0, 'django.contrib.postgres')

try:
    import django_extensions  # noqa
    INSTALLED_APPS.append('django_extensions')
except ImportError:
    pass

PLUGINS = []
for entry_point in iter_entry_points(group='pretix.plugin', name=None):
    if entry_point.module_name in PRETIX_PLUGINS_EXCLUDE:
        continue
    PLUGINS.append(entry_point.module_name)
    INSTALLED_APPS.append(entry_point.module_name)

HIJACK_PERMISSION_CHECK = "hijack.permissions.superusers_and_staff"
HIJACK_INSERT_BEFORE = None


REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'pretix.api.auth.permission.EventPermission',
    ],
    'DEFAULT_PAGINATION_CLASS': 'pretix.api.pagination.Pagination',
    'DEFAULT_VERSIONING_CLASS': 'rest_framework.versioning.NamespaceVersioning',
    'PAGE_SIZE': 50,
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'pretix.api.auth.token.TeamTokenAuthentication',
        'pretix.api.auth.device.DeviceTokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
        'oauth2_provider.contrib.rest_framework.OAuth2Authentication',
    ),
    'DEFAULT_RENDERER_CLASSES': (
        'drf_ujson.renderers.UJSONRenderer',
    ),
    'DEFAULT_PARSER_CLASSES': (
        'drf_ujson.parsers.UJSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser'
    ),
    'TEST_REQUEST_RENDERER_CLASSES': [
        'rest_framework.renderers.MultiPartRenderer',
        'rest_framework.renderers.JSONRenderer',
        'pretix.testutils.api.UploadRenderer',
    ],
    'EXCEPTION_HANDLER': 'pretix.api.exception.custom_exception_handler',
    'UNICODE_JSON': False
}


CORE_MODULES = {
    "pretix.base",
    "pretix.presale",
    "pretix.control",
    "pretix.plugins.checkinlists",
    "pretix.plugins.reports",
}

MIDDLEWARE = [
    'pretix.helpers.logs.RequestIdMiddleware',
    'pretix.api.middleware.IdempotencyMiddleware',
    'pretix.multidomain.middlewares.MultiDomainMiddleware',
    'pretix.base.middleware.CustomCommonMiddleware',
    'pretix.multidomain.middlewares.SessionMiddleware',
    'pretix.multidomain.middlewares.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'hijack.middleware.HijackUserMiddleware',
    'pretix.control.middleware.PermissionMiddleware',
    'pretix.control.middleware.AuditLogMiddleware',
    'pretix.base.middleware.LocaleMiddleware',
    'pretix.base.middleware.SecurityMiddleware',
    'pretix.presale.middleware.EventMiddleware',
    'pretix.api.middleware.ApiScopeMiddleware',
]

try:
    import debug_toolbar.settings  # noqa
    if DEBUG:
        INSTALLED_APPS.append('debug_toolbar.apps.DebugToolbarConfig')
        MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')
        DEBUG_TOOLBAR_PATCH_SETTINGS = False
        DEBUG_TOOLBAR_CONFIG = {
            'JQUERY_URL': '',
            'DISABLE_PANELS': debug_toolbar.settings.PANELS_DEFAULTS,
        }
    pass
except ImportError:
    pass


if METRICS_ENABLED:
    MIDDLEWARE.insert(MIDDLEWARE.index('pretix.base.middleware.CustomCommonMiddleware') + 1,
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

LOCALE_PATHS = [
    os.path.join(os.path.dirname(__file__), 'locale'),
]
if config.has_option('languages', 'path'):
    LOCALE_PATHS.insert(0, config.get('languages', 'path'))

FORMAT_MODULE_PATH = [
    'pretix.helpers.formats',
]

ALL_LANGUAGES = [
    ('en', _('English')),
    ('de', _('German')),
    ('de-informal', _('German (informal)')),
    ('ar', _('Arabic')),
    ('zh-hans', _('Chinese (simplified)')),
    ('cs', _('Czech')),
    ('da', _('Danish')),
    ('nl', _('Dutch')),
    ('nl-informal', _('Dutch (informal)')),
    ('fr', _('French')),
    ('fi', _('Finnish')),
    ('gl', _('Galician')),
    ('el', _('Greek')),
    ('it', _('Italian')),
    ('lv', _('Latvian')),
    ('pl', _('Polish')),
    ('pt-pt', _('Portuguese (Portugal)')),
    ('pt-br', _('Portuguese (Brazil)')),
    ('ro', _('Romanian')),
    ('ru', _('Russian')),
    ('es', _('Spanish')),
    ('tr', _('Turkish')),
    ('uk', _('Ukrainian')),
]
LANGUAGES_OFFICIAL = {
    'en', 'de', 'de-informal'
}
LANGUAGES_INCUBATING = {
    'pl', 'fi', 'pt-br', 'gl', 'cs'
} - set(config.get('languages', 'allow_incubating', fallback='').split(','))
LANGUAGES_RTL = {
    'ar', 'hw'
}
LANGUAGES = []
LANGUAGES_ENABLED = [lang for lang in config.get("languages", "enabled", fallback='').split(',') if lang]
for k, v in ALL_LANGUAGES:
    if not DEBUG and k in LANGUAGES_INCUBATING:
        continue
    if LANGUAGES_ENABLED and k not in LANGUAGES_ENABLED:
        continue
    LANGUAGES.append((k, v))


EXTRA_LANG_INFO = {
    'de-informal': {
        'bidi': False,
        'code': 'de-informal',
        'name': 'German (informal)',
        'name_local': 'Deutsch',
        'public_code': 'de',
    },
    'nl-informal': {
        'bidi': False,
        'code': 'nl-informal',
        'name': 'Dutch (informal)',
        'name_local': 'Nederlands',
        'public_code': 'nl',
    },
    'fr': {
        'bidi': False,
        'code': 'fr',
        'name': 'French',
        'name_local': 'Français'
    },
    'lv': {
        'bidi': False,
        'code': 'lv',
        'name': 'Latvian',
        'name_local': 'Latviešu'
    },
    'pt-pt': {
        'bidi': False,
        'code': 'pt-pt',
        'name': 'Portuguese',
        'name_local': 'Português',
    },
}

django.conf.locale.LANG_INFO.update(EXTRA_LANG_INFO)


AUTH_USER_MODEL = 'pretixbase.User'
LOGIN_URL = 'control:auth.login'
LOGIN_URL_CONTROL = 'control:auth.login'
CSRF_FAILURE_VIEW = 'pretix.base.views.errors.csrf_failure'

template_loaders = (
    'django.template.loaders.filesystem.Loader',
    'pretix.helpers.template_loaders.AppLoader',
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
                'pretix.base.context.contextprocessor',
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
    ('text/vue', 'pretix.helpers.compressor.VueCompiler'),
)

COMPRESS_OFFLINE_CONTEXT = {
    'basetpl': 'empty.html',
}

COMPRESS_ENABLED = COMPRESS_OFFLINE = not debug_fallback

COMPRESS_FILTERS = {
    'css': (
        # CssAbsoluteFilter is incredibly slow, especially when dealing with our _flags.scss
        # However, we don't need it if we consequently use the static() function in Sass
        # 'compressor.filters.css_default.CssAbsoluteFilter',
        'compressor.filters.cssmin.rCSSMinFilter',
    ),
    'js': (
        'compressor.filters.jsmin.JSMinFilter',
    )
}

INTERNAL_IPS = ('127.0.0.1', '::1')

MESSAGE_TAGS = {
    messages.INFO: 'alert-info',
    messages.ERROR: 'alert-danger',
    messages.WARNING: 'alert-warning',
    messages.SUCCESS: 'alert-success',
}
MESSAGE_STORAGE = 'django.contrib.messages.storage.session.SessionStorage'

loglevel = 'DEBUG' if DEBUG else config.get('pretix', 'loglevel', fallback='INFO')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': (
                '%(levelname)s %(asctime)s RequestId=%(request_id)s %(name)s %(module)s %(message)s'
                if REQUEST_ID_HEADER
                else '%(levelname)s %(asctime)s %(name)s %(module)s %(message)s'
            )
        },
    },
    'filters': {
        'require_admin_enabled': {
            '()': 'pretix.helpers.logs.AdminExistsFilter',
        },
        'request_id': {
            '()': 'pretix.helpers.logs.RequestIdFilter'
        },
    },
    'handlers': {
        'console': {
            'level': loglevel,
            'class': 'logging.StreamHandler',
            'formatter': 'default',
            'filters': ['request_id'],
        },
        'csp_file': {
            'level': loglevel,
            'class': 'logging.FileHandler',
            'filename': os.path.join(LOG_DIR, 'csp.log'),
            'formatter': 'default',
            'filters': ['request_id'],
        },
        'file': {
            'level': loglevel,
            'class': 'logging.FileHandler',
            'filename': os.path.join(LOG_DIR, 'pretix.log'),
            'formatter': 'default',
            'filters': ['request_id'],
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
            'filters': ['require_admin_enabled']
        },
        'null': {
            'class': 'logging.NullHandler',
        },
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
        'django.security.DisallowedHost': {
            'handlers': ['null'],
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['file', 'console'],
            'level': 'INFO',  # Do not output all the queries
            'propagate': False,
        },
        'asyncio': {
            'handlers': ['file', 'console'],
            'level': 'WARNING',
        },
    },
}

SENTRY_ENABLED = False
if config.has_option('sentry', 'dsn') and not any(c in sys.argv for c in ('shell', 'shell_scoped', 'shell_plus')):
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.logging import (
        LoggingIntegration, ignore_logger,
    )

    from .sentry import PretixSentryIntegration, setup_custom_filters

    SENTRY_TOKEN = config.get('sentry', 'traces_sample_token', fallback='')

    def traces_sampler(sampling_context):
        qs = sampling_context.get('wsgi_environ', {}).get('QUERY_STRING', '')
        if SENTRY_TOKEN and SENTRY_TOKEN in qs:
            return 1.0
        return config.getfloat('sentry', 'traces_sample_rate', fallback=0.0)

    SENTRY_ENABLED = True
    sentry_sdk.init(
        dsn=config.get('sentry', 'dsn'),
        integrations=[
            PretixSentryIntegration(),
            CeleryIntegration(),
            LoggingIntegration(
                level=logging.INFO,
                event_level=logging.CRITICAL
            )
        ],
        traces_sampler=traces_sampler,
        environment=urlparse(SITE_URL).netloc,
        release=__version__,
        send_default_pii=False,
        propagate_traces=False,  # see https://github.com/getsentry/sentry-python/issues/1717
    )
    ignore_logger('pretix.base.tasks')
    ignore_logger('django.security.DisallowedHost')
    setup_custom_filters()

CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TASK_DEFAULT_QUEUE = 'default'
CELERY_TASK_QUEUES = (
    Queue('default', routing_key='default.#'),
    Queue('checkout', routing_key='checkout.#'),
    Queue('mail', routing_key='mail.#'),
    Queue('background', routing_key='background.#'),
    Queue('notifications', routing_key='notifications.#'),
)
CELERY_TASK_ROUTES = ([
    ('pretix.base.services.cart.*', {'queue': 'checkout'}),
    ('pretix.base.services.orders.*', {'queue': 'checkout'}),
    ('pretix.base.services.mail.*', {'queue': 'mail'}),
    ('pretix.base.services.update_check.*', {'queue': 'background'}),
    ('pretix.base.services.quotas.*', {'queue': 'background'}),
    ('pretix.base.services.waitinglist.*', {'queue': 'background'}),
    ('pretix.base.services.notifications.*', {'queue': 'notifications'}),
    ('pretix.api.webhooks.*', {'queue': 'notifications'}),
    ('pretix.presale.style.*', {'queue': 'background'}),
    ('pretix.plugins.banktransfer.*', {'queue': 'background'}),
],)

BOOTSTRAP3 = {
    'success_css_class': '',
    'field_renderers': {
        'default': 'bootstrap3.renderers.FieldRenderer',
        'inline': 'bootstrap3.renderers.InlineFieldRenderer',
        'control': 'pretix.control.forms.renderers.ControlFieldRenderer',
        'bulkedit': 'pretix.control.forms.renderers.BulkEditFieldRenderer',
        'bulkedit_inline': 'pretix.control.forms.renderers.InlineBulkEditFieldRenderer',
        'checkout': 'pretix.presale.forms.renderers.CheckoutFieldRenderer',
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
OAUTH2_PROVIDER_APPLICATION_MODEL = 'pretixapi.OAuthApplication'
OAUTH2_PROVIDER_GRANT_MODEL = 'pretixapi.OAuthGrant'
OAUTH2_PROVIDER_ACCESS_TOKEN_MODEL = 'pretixapi.OAuthAccessToken'
OAUTH2_PROVIDER_REFRESH_TOKEN_MODEL = 'pretixapi.OAuthRefreshToken'
OAUTH2_PROVIDER = {
    'SCOPES': {
        'profile': _('User profile only'),
        'read': _('Read access'),
        'write': _('Write access'),
    },
    'OAUTH2_VALIDATOR_CLASS': 'pretix.api.oauth.Validator',
    'ALLOWED_REDIRECT_URI_SCHEMES': ['https'] if not DEBUG else ['http', 'https'],
    'ACCESS_TOKEN_EXPIRE_SECONDS': 3600 * 24,
    'ROTATE_REFRESH_TOKEN': False,

}

COUNTRIES_OVERRIDE = {
    'XK': _('Kosovo'),
}

DATA_UPLOAD_MAX_NUMBER_FIELDS = 25000
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB

# File sizes are in MiB
FILE_UPLOAD_MAX_SIZE_IMAGE = 1024 * 1024 * config.getint("pretix_file_upload", "max_size_image", fallback=10)
FILE_UPLOAD_MAX_SIZE_FAVICON = 1024 * 1024 * config.getint("pretix_file_upload", "max_size_favicon", fallback=1)
FILE_UPLOAD_MAX_SIZE_EMAIL_ATTACHMENT = 1024 * 1024 * config.getint("pretix_file_upload", "max_size_email_attachment", fallback=5)
FILE_UPLOAD_MAX_SIZE_EMAIL_AUTO_ATTACHMENT = 1024 * 1024 * config.getint("pretix_file_upload", "max_size_email_auto_attachment", fallback=1)
FILE_UPLOAD_MAX_SIZE_OTHER = 1024 * 1024 * config.getint("pretix_file_upload", "max_size_other", fallback=10)

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'  # sadly. we would prefer BigInt, and should use it for all new models but the migration will be hard
