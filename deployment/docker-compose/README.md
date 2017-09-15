What is this?
-------------

This is a small example setup to run pretix with docker-compose.
This is for users who just want to try pretix and play around a bit.

__For production use, you need to harden the Dockerfile.__
 

Care Windows Users:
-------------------
Mabe you have to fix the /etc/pretix/pretix.cfg url _localhost -> http://192.168.99.100_ (or what ever ip your docker-machine is running)


RUN:
----
Please check the content of ```run.sh``` before you run it, if the (named) dockercontainer already exists it will be recreated and replaced with this one.

```bash
./run.sh
```
