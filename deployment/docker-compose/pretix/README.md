# Example docker-compose setup

## What is this?

This is a small example setup to run pretix with docker-compose.

## Prepare

* Change the `pretix/etc/pretix.cfg` to fit your needs
* Change the `.dbenv` to fit the `pretix.cfg`
* Copy the content of `../../../src` into `src_tmp`

## Run with nginx container

```bash
docker-compose -f docker-compose.yml -f docker-compose.nginx.yml up --force-recreate --build
```

No volumes are shared with the host.
Named Volumes will be used instead.

## Run without nginx container

```bash
docker-compose up --force-recreate --build
```

## Run with nginx and existing haproxy

### Preparation

* A working haproxy setup
* A precreated transfer network named `HAProxy2Pretix` with your haproxy having `10.255.0.1/30`
* Your haproxy is lookign for pretix on the ip `10.255.0.2` on the `HAProxy2Pretix` interface

### Starting

```bash
docker-compose -f docker-compose.yml -f docker-compose.nginx.yml -f docker-compose.toHAProxy.yml up --force-recreate --build
```
