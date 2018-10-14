FROM ubuntu:latest

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && echo "postfix postfix/main_mailer_type select Internet Site" | debconf-set-selections \
    && echo "postfix postfix/mailname string mysubdomain.mydomain.com" | debconf-set-selections \
    && apt-get install -y postfix mailutils inetutils-syslogd locales \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
RUN sed -i 's_^mynetworks = .*$_mynetworks = 0.0.0.0/0 [::]/0_g' /etc/postfix/main.cf
RUN mkdir -p /var/spool/postfix/etc/ssl && chown -R postfix /var/spool/postfix

COPY entrypoint.sh /

ENTRYPOINT [ "/entrypoint.sh" ]
