#!/usr/bin/env bash

echo "Sleep 5 sec: Avoid racecondition with db"
sleep 5
python3 manage.py compilemessages
python3 manage.py compilejsi18n
python3 manage.py collectstatic --noinput
python3 manage.py compress
python3 -m pretix migrate --noinput
uwsgi uwsgi.ini