#!/usr/bin/env bash

echo "Sleep 30 sec: Avoid racecondition with db"
sleep 15s
python3 manage.py compilemessages
python3 manage.py compilejsi18n
python3 manage.py collectstatic --noinput
python3 manage.py compress
python3 -m pretix migrate --noinput
uwsgi --ini /etc/pretix/pretix.cfg