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

import os

import django.conf.locale
from pycountry import currencies

from django.utils.translation import gettext_lazy as _  # NOQA

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

USE_I18N = True
USE_TZ = True

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
    'djangoformsetjs',
    'compressor',
    'bootstrap3',
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
    'django_countries',
    'oauth2_provider',
    'phonenumber_field',
    'statici18n',
    'django.forms',  # after pretix.base for overrides
]

FORMAT_MODULE_PATH = [
    'pretix.helpers.formats',
]

ALL_LANGUAGES = [
    ('en', _('English')),
    ('de', _('German')),
    ('de-informal', _('German (informal)')),
    ('ar', _('Arabic')),
    ('zh-hans', _('Chinese (simplified)')),
    ('zh-hant', _('Chinese (traditional)')),
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
LANGUAGES_RTL = {
    'ar', 'hw'
}
LANGUAGES_INCUBATING = {
    'pl', 'fi', 'pt-br', 'gl',
}
LOCALE_PATHS = [
    os.path.join(os.path.dirname(__file__), 'locale'),
]

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

template_loaders = (
    'django.template.loaders.filesystem.Loader',
    'pretix.helpers.template_loaders.AppLoader',
)

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
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

FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

STATIC_ROOT = os.path.join(os.path.dirname(__file__), 'static.dist')

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

COMPRESS_ENABLED = True
COMPRESS_OFFLINE = True

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

PRETIX_EMAIL_NONE_VALUE = 'none@well-known.pretix.eu'
PRETIX_PRIMARY_COLOR = '#8E44B3'

# pretix includes caching options for some special situations where full HTML responses are cached. This might be
# stressful for some cache setups so it is enabled by default and currently can't be enabled through pretix.cfg
CACHE_LARGE_VALUES_ALLOWED = False
CACHE_LARGE_VALUES_ALIAS = 'default'
