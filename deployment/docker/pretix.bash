#!/bin/bash
cd /pretix/src
export DJANGO_SETTINGS_MODULE=production_settings
export DATA_DIR=/data/
export HOME=/pretix

AUTOMIGRATE=${AUTOMIGRATE:-yes}
NUM_WORKERS_DEFAULT=$((2 * $(nproc --all)))
export NUM_WORKERS=${NUM_WORKERS:-$NUM_WORKERS_DEFAULT}

if [ ! -d /data/logs ]; then
    mkdir /data/logs;
fi
if [ ! -d /data/media ]; then
    mkdir /data/media;
fi

if [ "$1" == "cron" ]; then
    exec python3 -m pretix runperiodic
fi

if [ "$AUTOMIGRATE" != "skip" ]; then
  python3 -m pretix migrate --noinput
fi

if [ "$1" == "all" ]; then
    exec sudo -E /usr/bin/supervisord -n -c /etc/supervisord.all.conf
fi

if [ "$1" == "web" ]; then
    exec sudo -E /usr/bin/supervisord -n -c /etc/supervisord.web.conf
fi

if [ "$1" == "webworker" ]; then
    exec gunicorn pretix.wsgi \
        --name pretix \
        --workers $NUM_WORKERS \
        --max-requests 1200 \
        --max-requests-jitter 50 \
        --log-level=info \
        --bind=unix:/tmp/pretix.sock
fi

if [ "$1" == "taskworker" ]; then
    shift
    exec celery -A pretix.celery_app worker -l info "$@"
fi

if [ "$1" == "upgrade" ]; then
    exec python3 -m pretix updatestyles
fi

exec python3 -m pretix "$@"
