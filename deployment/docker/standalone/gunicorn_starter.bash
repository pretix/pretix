#!/bin/bash
cd /pretix/src
export DJANGO_SETTINGS_MODULE=pretix.settings
export MEDIA_ROOT=/data/
python3 manage.py migrate
python3 manage.py compress
gunicorn \
	-b '0.0.0.0:80' \
	-w 3 --max-requests 1000 --max-requests-jitter 50 \
	pretix.wsgi
