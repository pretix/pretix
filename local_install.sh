#!/bin/bash
# https://docs.pretix.eu/en/latest/admin/installation/manual_smallscale.html

BASE=pretix_dev # pretix for production

# FIRST TIME ONLY
# sudo apt-get install nginx postgresql redis nodejs git build-essential python3-dev python3-venv python3 python3-pip libxml2-dev libxslt1-dev libffi-dev zlib1g-dev libssl-dev gettext libpq-dev libjpeg-dev libopenjp2-7-dev
# git clone git@github.com:carpentries/pretix.git
# sudo adduser pretix --disabled-password --home /var/pretix

# sudo -u postgres psql -c 'SHOW SERVER_ENCODING'
# sudo -u postgres createuser pretix
# sudo -u postgres createdb -O pretix $BASE
# sudo mkdir /etc/$BASE
# sudo touch /etc/$BASE/pretix.cfg
# sudo chown -R pretix:pretix /etc/$BASE/
# sudo chmod 0600 /etc/$BASE/pretix.cfg

# EDIT CONFIG
# sudo nano /etc/$BASE/pretix.cfg
# sudo mkdir /var/$BASE
# sudo chown -R pretix.pretix /var/$BASE
# cd /var/$BASE
# sudo -u pretix -s
# python3 -m venv /var/$BASE/venv
# mkdir -p /var/$BASE/data/media
# chmod +x /var/$BASE

source /var/pretix_dev/venv/bin/activate
pip install -U pip setuptools wheel gunicorn
pip install --target=static.dist .
python -m pretix migrate
cd src
make npminstall
cd ..
python -m pretix rebuild

#server {
#    listen 8347 default_server;
#    listen [::]:8347 ipv6only=on default_server;
#    server_name test-pretix;

#    location / {
#        proxy_pass http://localhost:8346;
#        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
#        proxy_set_header X-Forwarded-Proto http;
#        proxy_set_header Host $http_host;
#    }
#    location /media/ {
#        alias /var/pretix_dev/data/media/;
#        expires 7d;
#        access_log off;
#    }
#    location ^~ /media/cachedfiles {
#        deny all;
#        return 404;
#    }
#    location ^~ /media/invoices {
#        deny all;
#        return 404;
#    }
#    location /static/ {
#        alias /var/pretix_dev/build/lib/pretix/static.dist/;
#        access_log off;
#        expires 365d;
#        add_header Cache-Control "public";
#    }
#}

## once installed
source /var/pretix_dev/venv/bin/activate
rm -rf static.dist/ && pip install --target=static.dist .

## as a sudoer
sudo systemctl restart pretix-web pretix-worker nginx
