#!/usr/bin/env bash

echo "Sleep 1m: Avoid racecondition with db and pretix migrations"
sleep 1m
celery -A pretix.celery_app worker -l info
