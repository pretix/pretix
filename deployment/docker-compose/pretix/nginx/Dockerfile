FROM nginx:alpine

RUN \
    apk add --update curl && \
    addgroup -S www-data && \
    adduser -H -h /static -S -G www-data -s /bin/false www-data
RUN rm -rf /etc/nginx/conf.d/*
ADD nginx.conf /etc/nginx/nginx.conf
HEALTHCHECK --interval=1m30s --timeout=10s --retries=3 --start-period=5m \
    CMD curl -f http://localhost/ || exit 1

VOLUME /static
