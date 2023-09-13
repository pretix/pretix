FROM python:3.11-bookworm

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
            build-essential \
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
            python3-virtualenv \
            python3-dev \
            sudo \
            supervisor \
            libmaxminddb0 \
            libmaxminddb-dev \
            zlib1g-dev \
            nodejs  \
            npm && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    dpkg-reconfigure locales &&  \
    locale-gen C.UTF-8 &&  \
    /usr/sbin/update-locale LANG=C.UTF-8 && \
    mkdir /etc/pretix && \
    mkdir /data && \
    useradd -ms /bin/bash -d /pretix -u 15371 pretixuser && \
    echo 'pretixuser ALL=(ALL) NOPASSWD:SETENV: /usr/bin/supervisord' >> /etc/sudoers && \
    mkdir /static && \
    mkdir /etc/supervisord


ENV LC_ALL=C.UTF-8 \
    DJANGO_SETTINGS_MODULE=production_settings

COPY deployment/docker/pretix.bash /usr/local/bin/pretix
COPY deployment/docker/supervisord /etc/supervisord
COPY deployment/docker/supervisord.all.conf /etc/supervisord.all.conf
COPY deployment/docker/supervisord.web.conf /etc/supervisord.web.conf
COPY deployment/docker/nginx.conf /etc/nginx/nginx.conf
COPY deployment/docker/nginx-max-body-size.conf /etc/nginx/conf.d/nginx-max-body-size.conf
COPY deployment/docker/production_settings.py /pretix/src/production_settings.py
COPY pyproject.toml /pretix/pyproject.toml
COPY _build /pretix/_build
COPY src /pretix/src

RUN pip3 install -U \
        pip \
        setuptools \
        wheel && \
    cd /pretix && \
    PRETIX_DOCKER_BUILD=TRUE pip3 install \
        -e ".[memcached]" \
        gunicorn django-extensions ipython && \
    rm -rf ~/.cache/pip

RUN chmod +x /usr/local/bin/pretix && \
    rm /etc/nginx/sites-enabled/default && \
    cd /pretix/src && \
    rm -f pretix.cfg &&  \
    mkdir -p data && \
    chown -R pretixuser:pretixuser /pretix /data data &&  \
    sudo -u pretixuser make production

USER pretixuser
VOLUME ["/etc/pretix", "/data"]
EXPOSE 80
ENTRYPOINT ["pretix"]
CMD ["all"]
