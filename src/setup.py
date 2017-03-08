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
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Intended Audience :: Other Audience',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Framework :: Django :: 1.10'
    ],

    keywords='tickets web shop ecommerce',
    install_requires=[
        'Django==1.10.*',
        'python-dateutil==2.4.*',
        'pytz',
        'django-bootstrap3==7.1.*',
        'django-formset-js-improved==0.5.0.1',
        'django-compressor==2.1',
        'reportlab==3.2.*',
        'easy-thumbnails==2.*',
        'PyPDF2==1.26.*',
        'django-libsass',
        'libsass',
        'django-otp==0.3.*',
        'python-u2flib-server==4.*',
        'django-formtools==1.0',
        'celery==4.0.2',
        'kombu==4.0.2',
        'django-statici18n==1.3.*',
        'inlinestyler==0.2.*',
        'BeautifulSoup4',
        'html5lib<0.99999999,>=0.999',
        'slimit',
        'lxml',
        'static3==0.6.1',
        'dj-static',
        'csscompressor',
        'django-markup',
        'markdown',
        'bleach==1.5',
        'raven',
        'paypalrestsdk==1.12.*',
        'pycparser==2.13',
        'django-redis==4.1.*',
        'redis==2.10.5',
        'stripe==1.22.*',
        'chardet>=2.3,<3',
        'mt-940==3.2',
        'django-i18nfield'
    ],
    extras_require={
        'dev': [
            'django-debug-toolbar==1.5',
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
            'pytest-warnings'
        ],
        'memcached': ['pylibmc'],
        'mysql': ['mysqlclient'],
        'postgres': ['psycopg2'],
    },

    packages=find_packages(exclude=['tests', 'tests.*']),
    include_package_data=True,
    cmdclass=cmdclass,
)
