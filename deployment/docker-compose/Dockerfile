FROM python:3.6

RUN apt-get update
RUN apt-get install -y git libxml2-dev libxslt1-dev python-dev python-virtualenv locales \
    libffi-dev build-essential python3-dev zlib1g-dev libssl-dev gettext libpq-dev \
    libmysqlclient-dev libjpeg-dev sudo

RUN apt-get clean
RUN rm -rf /var/lib/apt/lists/* && \
    dpkg-reconfigure locales && \
	locale-gen C.UTF-8 && \
	/usr/sbin/update-locale LANG=C.UTF-8

RUN useradd -ms /bin/bash -d /pretix -u 15371 pretixuser

RUN mkdir /etc/pretix
RUN mkdir /data
RUN mkdir /static

ENV LC_ALL=C.UTF-8
ENV DJANGO_SETTINGS_MODULE=production_settings

WORKDIR /pretix/src

RUN rm -f pretix.cfg
COPY ./src_tmp .
COPY ./pretix/production_settings.py .
COPY ./pretix/uwsgi.ini .
COPY ./pretix/docker-entrypoint.sh .

RUN pip3 install -U pip wheel setuptools uwsgi
RUN pip3 install -r requirements.txt -r requirements/mysql.txt -r requirements/redis.txt

RUN mkdir -p data
RUN chown -R pretixuser:pretixuser /pretix /data data

USER pretixuser
COPY ./pretix/etc/pretix.cfg /etc/pretix/pretix.cfg
