FROM python:3.6

ENV DEBIAN_FRONTEND=noninteractive
ENV LC_ALL=C.UTF-8
ENV DJANGO_SETTINGS_MODULE=production_settings

RUN apt-get update \
    && apt-get install -y git libxml2-dev libxslt1-dev python-dev python-virtualenv locales \
        libffi-dev build-essential python3-dev zlib1g-dev libssl-dev gettext libpq-dev \
        default-libmysqlclient-dev libjpeg-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN dpkg-reconfigure locales \
	&& locale-gen C.UTF-8 \
	&& /usr/sbin/update-locale LANG=C.UTF-8
RUN mkdir /etc/pretix /data /static
RUN pip3 install -U pip wheel setuptools uwsgi

WORKDIR /pretix/src

COPY pretix/etc/pretix.cfg /etc/pretix/pretix.cfg
COPY ./src_tmp .
COPY pretix/production_settings.py .
COPY pretix .
COPY pretix-entrypoint.sh .
COPY task-entrypoint.sh .

RUN pip3 install -r requirements/production.txt \
    && pip3 install -r requirements/mysql.txt \
    && pip3 install -r requirements/redis.txt
RUN chmod +x pretix-entrypoint.sh task-entrypoint.sh \
    && chown -R www-data:www-data /pretix /etc/pretix /data /static
