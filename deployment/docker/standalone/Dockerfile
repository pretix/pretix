FROM debian:jessie

RUN apt-get update && apt-get install -y supervisor python3 git python3-pip \
	libxml2-dev libxslt1-dev python-dev python-virtualenv locales libffi-dev \
	build-essential python3-dev  --no-install-recommends

RUN dpkg-reconfigure locales && \
	locale-gen C.UTF-8 && \
	/usr/sbin/update-locale LANG=C.UTF-8
ENV LC_ALL C.UTF-8

RUN apt-get clean && rm -rf /var/lib/apt/lists/*

ADD supervisord.conf /etc/supervisor/conf.d/supervisord.conf
ADD gunicorn_starter.bash /gunicorn_starter.bash
ADD src /src
WORKDIR /src
RUN pip3 install -r requirements.txt
RUN pip3 install gunicorn

EXPOSE 80
CMD ["/usr/bin/supervisord"]

