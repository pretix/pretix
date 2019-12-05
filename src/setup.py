import os
import sys
from codecs import open
from distutils.command.build import build
from os import path

from setuptools import find_packages, setup

from pretix import __version__

CURRENT_PYTHON = sys.version_info[:2]
REQUIRED_PYTHON = (3, 5)
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

# Get the long description from the relevant file
try:
    with open(path.join(here, '../README.rst'), encoding='utf-8') as f:
        long_description = f.read()
except:
    long_description = ''


class CustomBuild(build):
    def run(self):
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pretix.settings")
        import django
        django.setup()
        from django.conf import settings
        from django.core import management

        settings.COMPRESS_ENABLED = True
        settings.COMPRESS_OFFLINE = True

        management.call_command('compilemessages', verbosity=1)
        management.call_command('compilejsi18n', verbosity=1)
        management.call_command('collectstatic', verbosity=1, interactive=False)
        management.call_command('compress', verbosity=1)
        build.run(self)


cmdclass = {
    'build': CustomBuild
}


setup(
    name='pretix',
    version=__version__,
    python_requires='>={}.{}'.format(*REQUIRED_PYTHON),
    description='Reinventing presales, one ticket at a time',
    long_description=long_description,
    url='https://pretix.eu',
    author='Raphael Michel',
    author_email='mail@raphaelmichel.de',
    license='Apache License 2.0',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Intended Audience :: Other Audience',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Environment :: Web Environment',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Framework :: Django :: 2.2'
    ],

    keywords='tickets web shop ecommerce',
    install_requires=[
        'Django==2.2.*',
        'djangorestframework==3.9.*',
        'python-dateutil==2.8.*',
        'requests==2.21.*',
        'pytz',
        'django-bootstrap3==11.0.*',
        'django-formset-js-improved==0.5.0.2',
        'django-compressor==2.2.*',
        'django-hierarkey==1.0.*,>=1.0.2',
        'django-filter==2.1.*',
        'django-scopes==1.1.*',
        'reportlab>=3.5.18',
        'Pillow==6.*',
        'PyPDF2==1.26.*',
        'django-libsass',
        'libsass',
        'django-otp==0.5.*',
        'webauthn==0.4.*',
        'python-u2flib-server==4.*',
        'django-formtools==2.1',
        'celery==4.3.*',
        'kombu==4.5.*',
        'django-statici18n==1.8.*',
        'inlinestyler==0.2.*',
        'BeautifulSoup4==4.7.*',
        'slimit',
        'lxml',
        'static3==0.7.*',
        'dj-static',
        'csscompressor',
        'django-markup',
        'markdown<=2.2',
        'bleach==3.1.*',
        'sentry-sdk==0.7.*',
        'babel',
        'paypalrestsdk==1.13.*',
        'pycparser==2.13',
        'django-redis==4.10.*',
        'redis==3.2.*',
        'stripe==2.32.*',
        'chardet<3.1.0,>=3.0.2',
        'mt-940==3.2',
        'django-i18nfield>=1.4.0',
        'django-jsonfallback>=2.1.2',
        'psycopg2-binary',
        'vobject==0.9.*',
        'pycountry',
        'django-countries',
        'pyuca',
        'defusedcsv>=1.1.0',
        'vat_moss==0.11.0',
        'django-localflavor>=2.2',
        'django-localflavor',
        'jsonschema',
        'django-hijack>=2.1.10,<2.2.0',
        'openpyxl',
        'django-oauth-toolkit==1.2.*',
        'oauthlib==2.1.*',
        'urllib3==1.24.*',  # required by current requests
        'django-phonenumber-field==3.0.*',
        'phonenumberslite==8.10.*',
    ],
    extras_require={
        'dev': [
            'django-debug-toolbar==1.11',
            'sqlparse==0.3.*',
            'pycodestyle==2.5.*',
            'pyflakes==2.1.*',
            'flake8==3.7.*',
            'pep8-naming',
            'coveralls',
            'coverage',
            'pytest==4.4.*',
            'pytest-django',
            'pytest-xdist==1.28.*',
            'isort',
            'pytest-mock==1.10.*',
            'pytest-rerunfailures==7.*',
            'responses',
            'potypo',
            'freezegun',
        ],
        'memcached': ['pylibmc'],
        'mysql': ['mysqlclient'],
    },

    packages=find_packages(exclude=['tests', 'tests.*']),
    include_package_data=True,
    cmdclass=cmdclass,
)
