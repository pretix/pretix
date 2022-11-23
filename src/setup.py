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
# This file contains Apache-licensed contributions copyrighted by: Claudio Luck, FlaviaBastos, Katharina Bogad, Laura
# Klünder, Lukas Bockstaller, Matthew Emerson, Tobias Kunze, jasonwaiting@live.hk
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import os
import subprocess
import sys
from codecs import open
from distutils.command.build import build
from distutils.command.build_ext import build_ext
from distutils.dir_util import copy_tree
from os import path

from setuptools import find_packages, setup

try:
    from pretix import __version__
except:
    if "PRETIX_DOCKER_BUILD" in os.environ:
        __version__ = "0.0.0"  # this is a hack to allow calling this file early in our docker build to make use of caching
    else:
        raise

CURRENT_PYTHON = sys.version_info[:2]
REQUIRED_PYTHON = (3, 6)
if CURRENT_PYTHON < REQUIRED_PYTHON:
    sys.stderr.write("""
==========================
Unsupported Python version
==========================
This version of pretix requires Python {}.{}, but you're trying to
install it on Python {}.{}.
This may be because you are using a version of pip that doesn't
understand the python_requires classifier. Make sure you
have pip >= 9.0 and setuptools >= 24.2, then try again:
    $ python -m pip install --upgrade pip setuptools
    $ python -m pip install pretix
This will install the latest version of pretix which works on your
version of Python. If you can't upgrade your pip (or Python), request
an older version of pretix:
    $ python -m pip install "pretix<2"
""".format(*(REQUIRED_PYTHON + CURRENT_PYTHON)))
    sys.exit(1)

here = path.abspath(path.dirname(__file__))
npm_installed = False

# Get the long description from the relevant file
try:
    with open(path.join(here, '../README.rst'), encoding='utf-8') as f:
        long_description = f.read()
except:
    long_description = ''


def npm_install():
    global npm_installed

    if not npm_installed:
        # keep this in sync with Makefile!
        node_prefix = os.path.join(here, 'pretix', 'static.dist', 'node_prefix')
        os.makedirs(node_prefix, exist_ok=True)
        copy_tree(os.path.join(here, 'pretix', 'static', 'npm_dir'), node_prefix)
        subprocess.check_call('npm install', shell=True, cwd=node_prefix)
        npm_installed = True


class CustomBuild(build):
    def run(self):
        if "PRETIX_DOCKER_BUILD" in os.environ:
            return  # this is a hack to allow calling this file early in our docker build to make use of caching
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pretix.settings")
        os.environ.setdefault("PRETIX_IGNORE_CONFLICTS", "True")
        import django
        django.setup()
        from django.conf import settings
        from django.core import management

        settings.COMPRESS_ENABLED = True
        settings.COMPRESS_OFFLINE = True

        npm_install()
        management.call_command('compilemessages', verbosity=1)
        management.call_command('compilejsi18n', verbosity=1)
        management.call_command('collectstatic', verbosity=1, interactive=False)
        management.call_command('compress', verbosity=1)

        build.run(self)


class CustomBuildExt(build_ext):
    def run(self):
        if "PRETIX_DOCKER_BUILD" in os.environ:
            return  # this is a hack to allow calling this file early in our docker build to make use of caching
        npm_install()
        build_ext.run(self)


cmdclass = {
    'build': CustomBuild,
    'build_ext': CustomBuildExt,
}


setup(
    name='pretix',
    version=__version__,
    python_requires='>={}.{}'.format(*REQUIRED_PYTHON),
    description='Reinventing presales, one ticket at a time',
    long_description=long_description,
    url='https://pretix.eu',
    author='Raphael Michel',
    author_email='support@pretix.eu',
    license='GNU Affero General Public License v3 with Additional Terms',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Intended Audience :: Other Audience',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Environment :: Web Environment',
        'License :: OSI Approved :: GNU Affero General Public License v3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Framework :: Django :: 3.2'
    ],

    keywords='tickets web shop ecommerce',
    install_requires=[
        'arabic-reshaper==2.1.4',  # Support for Arabic in reportlab
        'babel',
        'BeautifulSoup4==4.11.*',
        'bleach==5.0.*',
        'celery==4.4.*',
        'chardet==5.0.*',
        'cryptography>=3.4.2',
        'css-inline==0.8.*',
        'defusedcsv>=1.1.0',
        'dj-static',
        'Django==3.2.*',
        'django-bootstrap3==22.2.*',
        'django-compressor==4.1.*',
        'django-countries==7.4.*',
        'django-filter==22.1',
        'django-formset-js-improved==0.5.0.3',
        'django-formtools==2.4',
        'django-hierarkey==1.1.*',
        'django-hijack==3.2.*',
        'django-i18nfield==1.9.*,>=1.9.4',
        'django-libsass==0.9',
        'django-localflavor==3.1',
        'django-markup',
        'django-mysql',
        'django-oauth-toolkit==1.2.*',
        'django-otp==1.1.*',
        'django-phonenumber-field==7.0.*',
        'django-redis==5.2.*',
        'django-scopes==1.2.*',
        'django-statici18n==2.3.*',
        'djangorestframework==3.14.*',
        'dnspython<2.0',  # do not upgrade, causes issues with eventlet / gunicorn 19 and we cannot upgrade gunicorn right now
        'drf_ujson2==1.6.*',
        'isoweek',
        'jsonschema',
        'kombu==4.6.*',
        'libsass==0.22.*',
        'lxml',
        'markdown==3.3.4',  # 3.3.5 requires importlib-metadata>=4.4, but django-bootstrap3 requires importlib-metadata<3.
        # We can upgrade markdown again once django-bootstrap3 upgrades or once we drop Python 3.6 and 3.7
        'mt-940==4.23.*',
        'oauthlib==3.2.*',
        'openpyxl==3.0.*',
        'packaging',
        'paypalrestsdk==1.13.*',
        'paypal-checkout-serversdk==1.0.*',
        'PyJWT==2.6.*',
        'phonenumberslite==8.13.*',
        'Pillow==9.3.*',
        'protobuf==4.21.*',
        'psycopg2-binary',
        'pycountry',
        'pycparser==2.21',
        'pycryptodome==3.15.*',
        'PyPDF2==2.11.*',
        'python-bidi==0.4.*',  # Support for Arabic in reportlab
        'python-dateutil==2.8.*',
        'python-u2flib-server==4.*',
        'pytz',
        'pyuca',
        'redis==4.3.*',
        'reportlab==3.6.*',
        'requests==2.28.*',
        'sentry-sdk==1.10.*',  # when upgrading, check https://github.com/getsentry/sentry-python/issues/1700
        'sepaxml==2.6.*',
        'slimit',
        'static3==0.7.*',
        'stripe==5.0.*',
        'text-unidecode==1.*',
        'tlds>=2020041600',
        'tqdm==4.*',
        'vat_moss_forked==2020.3.20.0.11.0',
        'vobject==0.9.*',
        'webauthn==0.4.*',
        'zeep==4.2.*'
    ],
    extras_require={
        'dev': [
            'coverage',
            'coveralls',
            'django-debug-toolbar==3.7.*',
            'flake8==5.0.*',
            'freezegun',
            'isort==5.10.*',
            'pep8-naming==0.12.*',
            'potypo',
            'pycodestyle==2.9.*',
            'pyflakes==2.5.*',
            'pytest-cache',
            'pytest-cov',
            'pytest-django==4.*',
            'pytest-mock==3.10.*',
            'pytest-rerunfailures==10.2',
            'pytest-sugar',
            'pytest-xdist==3.0.*',
            'pytest==7.2.*',
            'responses',
        ],
        'memcached': ['pylibmc'],
        'mysql': ['mysqlclient'],
    },
    setup_requires=['setuptools-rust'],

    packages=find_packages(exclude=['tests', 'tests.*']),
    include_package_data=True,
    cmdclass=cmdclass,
)
