import os
from codecs import open
from distutils.command.build import build
from os import path

from setuptools import find_packages, setup

from pretix import __version__

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

        management.call_command('compilemessages', verbosity=1, interactive=False)
        management.call_command('compilejsi18n', verbosity=1, interactive=False)
        management.call_command('collectstatic', verbosity=1, interactive=False)
        management.call_command('compress', verbosity=1, interactive=False)
        build.run(self)


cmdclass = {
    'build': CustomBuild
}


setup(
    name='pretix',
    version=__version__,
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
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Framework :: Django :: 1.11'
    ],

    keywords='tickets web shop ecommerce',
    install_requires=[
        'Django==1.11.*',
        'djangorestframework==3.6.*',
        'python-dateutil==2.4.*',
        'pytz',
        'django-bootstrap3==8.2.*',
        'django-formset-js-improved==0.5.0.2',
        'django-compressor==2.1',
        'django-hierarkey==1.0.*,>=1.0.2',
        'django-filter==1.0.*',
        'reportlab==3.4.*',
        'easy-thumbnails==2.4.*',
        'PyPDF2==1.26.*',
        'django-libsass',
        'libsass',
        'django-otp==0.3.*',
        'python-u2flib-server==4.*',
        'django-formtools==2.0',
        'celery==4.1.*',
        'kombu==4.1.*',
        'django-statici18n==1.3.*',
        'inlinestyler==0.2.*',
        'BeautifulSoup4',
        'slimit',
        'lxml',
        'static3==0.6.1',
        'dj-static',
        'csscompressor',
        'django-markup',
        'markdown',
        'bleach==2.*',
        'raven',
        'babel',
        'paypalrestsdk==1.12.*',
        'pycparser==2.13',
        'django-redis==4.7.*',
        'redis==2.10.5',
        'stripe==1.62.*',
        'chardet<3.1.0,>=3.0.2',
        'mt-940==4.7',
        'django-i18nfield>=1.2.1',
        'vobject==0.9.*',
        'pycountry',
        'django-countries',
        'pyuca',
        'defusedcsv',
        'vat_moss==0.11.0',
        'django-hijack==2.1.*'
    ],
    extras_require={
        'dev': [
            'django-debug-toolbar==1.7',
            'sqlparse==0.2.1',
            'pep8==1.5.7',
            'pyflakes==1.1.0',
            'flake8',
            'pep8-naming',
            'coveralls',
            'coverage',
            'pytest==2.9.*',
            'pytest-django',
            'isort',
            'pytest-mock',
            'pytest-rerunfailures',
            'pytest-warnings',
            'responses'
        ],
        'memcached': ['pylibmc'],
        'mysql': ['mysqlclient'],
        'postgres': ['psycopg2'],
    },

    packages=find_packages(exclude=['tests', 'tests.*']),
    include_package_data=True,
    cmdclass=cmdclass,
)
