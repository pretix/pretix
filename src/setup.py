import os
from codecs import open
from distutils.command.build import build
from os import path

from setuptools import find_packages, setup

here = path.abspath(path.dirname(__file__))

# Get the long description from the relevant file
with open(path.join(here, '../README.md'), encoding='utf-8') as f:
    long_description = f.read()


class CustomBuild(build):
    def run(self):
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pretix.settings")
        import django
        django.setup()
        from django.conf import settings
        from django.core import management

        settings.COMPRESS_ENABLED = True
        settings.COMPRESS_OFFLINE = True

        management.call_command('collectstatic', verbosity=1, interactive=False)
        management.call_command('compress', verbosity=1, interactive=False)
        management.call_command('compilemessages', verbosity=1, interactive=False)
        build.run(self)


cmdclass = {
    'build': CustomBuild
}


setup(
    name='pretix',
    version='0.0.0',
    description='Reinventing ticket presales',
    long_description=long_description,
    url='http://pretix.eu',
    author='Raphael Michel',
    author_email='mail@raphaelmichel.de',
    license='Apache License 2.0',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Intended Audience :: Other Audience',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Framework :: Django :: 1.8'
    ],

    keywords='tickets web shop ecommerce',
    install_requires=[
        'Django>=1.9,<1.10', 'python-dateutil>=2.4,<2.5',
        'pytz', 'django-bootstrap3>=6.2,<6.3', 'django-formset-js',
        'django-compressor==2.0', 'reportlab>=3.2,<3.3',
        'easy-thumbnails>=2.2,<3'
        'PyPDF2', 'BeautifulSoup4', 'html5lib',
        'slimit', 'lxml', 'static3==0.6.1', 'dj-static', 'chardet',
        'csscompressor', 'defusedxml', 'mt-940', 'django-markup', 'markdown'
    ],
    extras_require={
        'dev': ['django-debug-toolbar>=1.3.0,<2.0'],
        'test': ['pep8==1.5.7', 'pyflakes', 'pep8-naming', 'flake8', 'coverage',
                 'pytest', 'pytest-django'],
        'memcached': ['pylibmc'],
        'mysql': ['mysqlclient'],
        'paypal': ['paypalrestsdk>=1.9,<1.10,<2.0'],
        'postgres': ['psycopg2'],
        'redis': ['django-redis>=4.1,<4.2', 'redis>=2.10,<2.11'],
        'stripe': ['stripe>=1.22,<1.23']
    },

    packages=find_packages(exclude=['tests', 'tests.*']),
    include_package_data=True,
    cmdclass=cmdclass
)
