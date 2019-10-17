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
fi

if [ "$1" == "style" ]; then
	XDG_CACHE_HOME=/cache pip3 install --no-use-pep517 -Ur src/requirements.txt -r src/requirements/dev.txt
	cd src
    flake8 .
    isort -c -rc -df .
fi
if [ "$1" == "doctests" ]; then
	XDG_CACHE_HOME=/cache pip3 install --no-use-pep517 -Ur doc/requirements.txt
	cd doc
	make doctest
fi
if [ "$1" == "doc-spelling" ]; then
	XDG_CACHE_HOME=/cache pip3 install --no-use-pep517 -Ur doc/requirements.txt
	cd doc
	make spelling
	if [ -s _build/spelling/output.txt ]; then
		exit 1
	fi
fi
if [ "$1" == "translation-spelling" ]; then
	XDG_CACHE_HOME=/cache pip3 install --no-use-pep517 -Ur src/requirements/dev.txt
	cd src
	potypo
fi
if [ "$1" == "tests" ]; then
	pip3 install -r src/requirements.txt --no-use-pep517 -Ur src/requirements/dev.txt
	cd src
	python manage.py check
	make all compress
	py.test --reruns 5 -n 3 tests
fi
if [ "$1" == "tests-cov" ]; then
	pip3 install -r src/requirements.txt --no-use-pep517 -Ur src/requirements/dev.txt
	cd src
	python manage.py check
	make all compress
	coverage run -m py.test --reruns 5 tests && codecov
fi
if [ "$1" == "plugins" ]; then
	pip3 install -r src/requirements.txt --no-use-pep517 -Ur src/requirements/dev.txt
	cd src
	python setup.py develop
	make all compress

	pushd ~
    git clone --depth 1 https://github.com/pretix/pretix-cartshare.git
    cd pretix-cartshare
    python setup.py develop
    make
	py.test --reruns 5 tests
    popd

fi
