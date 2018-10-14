#!/usr/bin/env bash

service inetutils-syslogd start
sleep 1s
service postfix start
exec tail -f /var/log/mail*