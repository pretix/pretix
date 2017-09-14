What is this?
-------------

This is a small example setup to run pretix with docker-compose.


Prepare
-------

- Change the pretix/etc/pretix.cfg to fit your needs
- Change the .dbenv to fit the pretix.cfg


Run with nginx container:
-------------------------

Remove these lines from docker-compose.yml

```bash
ports:
  - "0.0.0.0:8000:8000"
```

Run following command to start:
```bash
cp -r ../../../src src_tmp # Due to security reasons Docker cant build from parent directories
docker-compose -f docker-compose.yml -f docker-compose.nginx.yml up --force-recreate --build
```

No volumes are shared with the host. Named Volumes will be used.

Run without nginx container:
----------------------------

```bash
cd docker-compose/pretix
mkdir static data # Create the dirs by hand, otherwise they will belong to root
chown -R www-data:www-data static data
cp -r ../../../src src_tmp # Due to security reasons Docker cant build from parent directories
docker-compose up --force-recreate --build
```

__Shared host volumes:__

- ./static
- ./data

No data from the /static or /data location will be delivered. It's up to you how u deliver them. See nginx/nginx.conf for example
