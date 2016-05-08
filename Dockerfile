FROM debian:jessie

RUN apt-get update && apt-get install -y python3 git python3-pip \
	libxml2-dev libxslt1-dev python-dev python-virtualenv locales libffi-dev \
	build-essential python3-dev zlib1g-dev libssl-dev gettext git \
	libpq-dev libmysqlclient-dev libmemcached-dev libjpeg-dev \
	aqbanking-tools supervisor nginx sudo \
	--no-install-recommends

WORKDIR /

RUN dpkg-reconfigure locales && \
	locale-gen C.UTF-8 && \
	/usr/sbin/update-locale LANG=C.UTF-8
ENV LC_ALL C.UTF-8

RUN apt-get clean && rm -rf /var/lib/apt/lists/*

RUN useradd -ms /bin/bash -d /pretix -u 15371 pretixuser
RUN echo 'pretixuser ALL=(ALL) NOPASSWD: /usr/bin/supervisord' >> /etc/sudoers

RUN mkdir /etc/pretix
RUN mkdir /data
VOLUME /etc/pretix

COPY deployment/docker/pretix.bash /usr/local/bin/pretix
RUN chmod +x /usr/local/bin/pretix
COPY deployment/docker/supervisord.conf /etc/supervisord.conf

COPY deployment/docker/nginx.conf /etc/nginx/nginx.conf
RUN rm /etc/nginx/sites-enabled/default

COPY src /pretix/src
WORKDIR /pretix/src
ADD deployment/docker/production_settings.py /pretix/src/production_settings.py
ENV DJANGO_SETTINGS_MODULE production_settings

RUN pip3 install -r requirements.txt -r requirements/mysql.txt -r requirements/postgres.txt \
	-r requirements/memcached.txt -r requirements/celery.txt -r requirements/redis.txt \
	-r requirements/py34.txt gunicorn

RUN mkdir /static && chown -R pretixuser:pretixuser /static /pretix /data
USER pretixuser
RUN make production

EXPOSE 80

ENTRYPOINT ["pretix"]
CMD ["web"]
