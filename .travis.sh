#!/bin/bash
set -e
set -x

echo "Executing job $1"

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
	coverage run -m py.test --rerun 5 tests && coveralls
fi
