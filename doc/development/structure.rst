Project structure
=================

Python source code
------------------

All the source code lives in ``src/``, which has several subdirectories.

tixl/
    This directory contains the basic Django settings and URL routing. It is

tixlbase/
    This is the django app containing all the models and methods which are
    essential to all of tixl's features.

tixlcontrol/
    This is the django app containing the frontend for organizers.

tixlpresale/
    This is the django app containing the frontend for users buying tickets.
