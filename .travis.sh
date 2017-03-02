#!/bin/bash
set -e
set -x

echo "Executing job $1"

if [ "$PRETIX_CONFIG_FILE" == "tests/travis_mysql.cfg" ]; then
    mysql -u root -e 'CREATE DATABASE pretix DEFAULT CHARACTER SET utf8 DEFAULT COLLATE utf8_general_ci;'
    pip3 install -Ur src/requirements/mysql.txt
fi

if [ "$PRETIX_CONFIG_FILE" == "tests/travis_postgres.cfg" ]; then
    psql -c 'create database travis_ci_test;' -U postgres
    pip3 install -Ur src/requirements/postgres.txt
fi

if [ "$1" == "style" ]; then
	XDG_CACHE_HOME=/cache pip3 install -Ur src/requirements.txt -r src/requirements/dev.txt -r src/requirements/py34.txt
	cd src
    flake8 .
    isort -c -rc .
fi
if [ "$1" == "doctests" ]; then
	XDG_CACHE_HOME=/cache pip3 install -Ur doc/requirements.txt -r src/requirements/py34.txt
	cd doc
	make doctest
fi
if [ "$1" == "tests" ]; then
	pip3 install -r src/requirements.txt -Ur src/requirements/dev.txt -r src/requirements/py34.txt
	cd src
	python manage.py check
	make all compress
	coverage run -m py.test --rerun 5 tests && coverage report
fi
if [ "$1" == "tests-cov" ]; then
	pip3 install -r src/requirements.txt -Ur src/requirements/dev.txt -r src/requirements/py34.txt
	cd src
	python manage.py check
	make all compress
	coverage run -m py.test --rerun 5 tests && codecov
fi
