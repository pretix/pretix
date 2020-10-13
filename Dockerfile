FROM python:3.6

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
            build-essential \
            default-libmysqlclient-dev \
            gettext \
            git \
            libffi-dev \
            libjpeg-dev \
            libmemcached-dev \
            libpq-dev \
            libssl-dev \
            libxml2-dev \
            libxslt1-dev \
            locales \
            nginx \
            python-dev \
            python-virtualenv \
            python3-dev \
            sudo \
            supervisor \
            zlib1g-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    dpkg-reconfigure locales && \
	locale-gen C.UTF-8 && \
	/usr/sbin/update-locale LANG=C.UTF-8 && \
    mkdir /etc/pretix && \
    mkdir /data && \
    useradd -ms /bin/bash -d /pretix -u 15371 pretixuser && \
    echo 'pretixuser ALL=(ALL) NOPASSWD:SETENV: /usr/bin/supervisord' >> /etc/sudoers && \
    mkdir /static

ENV LC_ALL=C.UTF-8 \
    DJANGO_SETTINGS_MODULE=production_settings

# To copy only the requirements files needed to install from PIP
COPY src/requirements /pretix/src/requirements
COPY src/requirements.txt /pretix/src
RUN pip3 install -U \
        pip \
        setuptools \
        wheel && \
    cd /pretix/src && \
    pip3 install \
        -r requirements.txt \
        -r requirements/memcached.txt \
        -r requirements/mysql.txt \
        -r requirements/redis.txt \
        gunicorn && \
    rm -rf ~/.cache/pip

COPY deployment/docker/pretix.bash /usr/local/bin/pretix
COPY deployment/docker/supervisord.conf /etc/supervisord.conf
COPY deployment/docker/nginx.conf /etc/nginx/nginx.conf
COPY deployment/docker/production_settings.py /pretix/src/production_settings.py
COPY src /pretix/src

RUN cd /pretix/src && pip3 install .

RUN chmod +x /usr/local/bin/pretix && \
    rm /etc/nginx/sites-enabled/default && \
    cd /pretix/src && \
    rm -f pretix.cfg && \
	mkdir -p data && \
    chown -R pretixuser:pretixuser /pretix /data data && \
	sudo -u pretixuser make production

USER pretixuser
VOLUME ["/etc/pretix", "/data"]
EXPOSE 80
HEALTHCHECK --interval=1m --timeout=2m \
  CMD curl -fSs http://localhost/healthcheck/ || exit 1
ENTRYPOINT ["pretix"]
CMD ["all"]
