FROM python:3.6

RUN apt-get update && \
    apt-get install -y git libxml2-dev libxslt1-dev python-dev python-virtualenv locales \
      libffi-dev build-essential python3-dev zlib1g-dev libssl-dev gettext libpq-dev \
      default-libmysqlclient-dev libmemcached-dev libjpeg-dev supervisor nginx sudo \
	  --no-install-recommends && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    dpkg-reconfigure locales && \
	locale-gen C.UTF-8 && \
	/usr/sbin/update-locale LANG=C.UTF-8 && \
    mkdir /etc/pretix && \
    mkdir /data && \
    useradd -ms /bin/bash -d /pretix -u 15371 pretixuser && \
    echo 'pretixuser ALL=(ALL) NOPASSWD: /usr/bin/supervisord' >> /etc/sudoers && \
    mkdir /static

ENV LC_ALL=C.UTF-8 \
    DJANGO_SETTINGS_MODULE=production_settings

COPY deployment/docker/pretix.bash /usr/local/bin/pretix
COPY deployment/docker/supervisord.conf /etc/supervisord.conf
COPY deployment/docker/nginx.conf /etc/nginx/nginx.conf
COPY deployment/docker/production_settings.py /pretix/src/production_settings.py
COPY src /pretix/src

RUN chmod +x /usr/local/bin/pretix && \
    rm /etc/nginx/sites-enabled/default && \
    pip3 install -U pip wheel setuptools && \
    cd /pretix/src && \
    rm -f pretix.cfg && \
    pip3 install -r requirements.txt -r requirements/mysql.txt \
    	-r requirements/memcached.txt -r requirements/redis.txt gunicorn && \
	mkdir -p data && \
    chown -R pretixuser:pretixuser /pretix /data data && \
	sudo -u pretixuser make production

USER pretixuser
VOLUME ["/etc/pretix", "/data"]
EXPOSE 80
ENTRYPOINT ["pretix"]
CMD ["all"]
