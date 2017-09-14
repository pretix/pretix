FROM python:3.6

RUN apt-get update
RUN apt-get install -y git libxml2-dev libxslt1-dev python-dev python-virtualenv locales \
    libffi-dev build-essential python3-dev zlib1g-dev libssl-dev gettext libpq-dev \
    libmysqlclient-dev libjpeg-dev

RUN apt-get clean
RUN rm -rf /var/lib/apt/lists/* && \
    dpkg-reconfigure locales && \
	locale-gen C.UTF-8 && \
	/usr/sbin/update-locale LANG=C.UTF-8

ENV LC_ALL=C.UTF-8
ENV DJANGO_SETTINGS_MODULE=production_settings

RUN pip3 install -U pip wheel setuptools uwsgi

RUN mkdir /etc/pretix /data /static

COPY pretix/etc/pretix.cfg /etc/pretix/pretix.cfg

WORKDIR /pretix/src

COPY ./src_tmp .
COPY pretix/production_settings.py .

COPY pretix .
COPY pretix-entrypoint.sh .
COPY task-entrypoint.sh .

RUN chmod +x pretix-entrypoint.sh task-entrypoint.sh

RUN pip3 install -r requirements/production.txt
RUN pip3 install -r requirements/mysql.txt
RUN pip3 install -r requirements/redis.txt
RUN chown -R www-data:www-data /pretix /etc/pretix /data /static
