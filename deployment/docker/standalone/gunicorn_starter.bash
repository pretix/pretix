#!/bin/bash
cd /src
export DJANGO_SETTINGS_MODULE=pretix.settings
gunicorn \
	-b '0.0.0.0:80' \
	-w 3 --max-requests 1000 --max-requests-jitter 50 \
	pretix.wsgi
