What is this?
-------------

This is a small example setup to run pretix with docker-compose.

This  __IS NOT__ for production nor a drop in replacement for existing projects.

This __IS__ for users who just want to test pretix and play around a bit.
 
Changes to files:
-----------------
- fixed /etc/pretix/pretix.cfg for working sockets
- added /etc/cron.py for faking a cronjob in supervisord
- fixed /etc/supervisord.conf to run the /etc/cron.py
- fixed redis default config to create a socket instead a port (redis/redis.conf)
- added a run.sh for easy start (__DON'T RUN IT NOW__, continue reading please)


cron.py
-------
Takes 2 arguments: time and command e.g.:
```python
cron.py 1800 "echo 'blub' >> /tmp/blubblub"
```


Care Windows Users:
-------------------
Mabe you have to fix the /etc/pretix/pretix.cfg url _localhost -> http://192.168.99.100_ (or what ever ip your docker-machine is running)


RUN:
----
Due to racecondition on the first database startup i added a ```run.sh``` which will sleep 10 seconds to give the database some time to initialize

Please check the content of ```run.sh``` before you run it, if the (named) dockercontainer already exists it will be recreated and replaced with this one.

```bash
./run.sh
```

After the first run, it is normaly safe to run a clean

```bash
docker-compose up [--force-recreate --build -d]
```