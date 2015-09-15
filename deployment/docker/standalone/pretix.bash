#!/bin/bash
cd /pretix/src
export DJANGO_SETTINGS_MODULE=pretix.settings
export DATA_DIR=/data/
NUM_WORKERS=25

if [ ! -d /data/logs ]; then
    mkdir /data/logs;
fi
if [ ! -d /data/media ]; then
    mkdir /data/media;
fi

if [ "$1" == "web" ]; then
	python3 manage.py collectstatic --noinput
	python3 manage.py compress
    exec gunicorn pretix.wsgi \
        --name pretix \
        --workers $NUM_WORKERS \
        --max-requests 1200 \
        --max-requests-jitter 50 \
        --log-level=info \
        --bind=0.0.0.0:80
fi

if [ "$1" == "worker" ]; then
    exec celery -A pretix worker -l info
fi

if [ "$1" == "migrate" ]; then
    exec python manage.py migrate --noinput
fi

if [ "$1" == "shell" ]; then
    exec python manage.py shell
fi

echo "Specify argument: web|worker|migrate|shell"
exit 1
