# Always prefer setuptools over distutils
from setuptools import setup, find_packages
# To use a consistent encoding
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

# Get the long description from the relevant file
with open(path.join(here, '../README.md'), encoding='utf-8') as f:
    long_description = f.read()

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

    # What does your project relate to?
    keywords='tickets web shop ecommerce',
    packages=['pretix'],
    install_requires=[
        'Django>=1.8,<1.9', 'python-dateutil>=2.4,<2.5',
        'pytz', 'django-bootstrap3>=6.1,<6.2', 'django-formset-js',
        'cleanerversion>=1.5,<1.7', 'django-compressor>=1.6,<2.0',
        'reportlab>=3.1.44,<3.2', 'PyPDF2', 'BeautifulSoup4', 'html5lib',
        'slimit', 'lxml', 'static3==0.6.1', 'dj-static', 'chardet'
    ],
    extras_require={
        'dev': ['django-debug-toolbar>=1.3.0,<2.0'],
        'test': ['pep8==1.5.7', 'pyflakes', 'pep8-naming', 'flake8', 'coverage',
                 'selenium', 'pytest', 'pytest-django'],
        'memcached': ['pylibmc'],
        'mysql': ['mysqlclient'],
        'paypal': ['paypalrestsdk>=1.9,<1.10,<2.0'],
        'postgres': ['psycopg2'],
        'redis': ['django-redis>=4.1,<4.2', 'django-redis>=4.1,<4.2'],
        'stripe': ['stripe>=1.22,<1.23']
    },
    include_package_data=True,
)
