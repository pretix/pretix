Project structure
=================

Python source code
------------------

All the source code lives in ``src/``, which has several subdirectories.

tixl/
    This directory contains the basic Django settings and URL routing.

tixlbase/
    This is the django app containing all the models and methods which are
    essential to all of tixl's features.

tixlcontrol/
    This is the django app containing the frontend for organizers.

tixlpresale/
    This is the django app containing the frontend for users buying tickets.

helpers/
    Helpers contain a very few modules providing workarounds for low-level flaws in
    Django or installed 3rd-party packages, like a filter to combine the ``lessc``
    preprocessor with ``django-compressor``'s URL rewriting.

Language files
--------------
The language files live in ``locale/*/LC_MESSAGES/``.

Static files
-------------

LESS source code
^^^^^^^^^^^^^^^^

We use less as a preprocessor for CSS. Our own less code is built in the same
step as Bootstrap and FontAwesome, so their mixins etc. are fully available.

tixlcontrol
    tixlcontrol has two main LESS files, ``tixlcontrol/static/tixlcontrol/less/main.less`` and
    ``tixlcontrol/static/tixlcontrol/less/auth.less``, importing everything else.

3rd-party assets
^^^^^^^^^^^^^^^^

Bootstrap
    Bootstrap lives as a git submodule at ``tixlbase/static/bootstrap/``

Font Awesome
    Font Awesome lives as a git submodule at ``tixlbase/static/fontawesome/``

jQuery
    jQuery lives as a single JavaScript file in ``tixlbase/static/jquery/js/``

jQuery plugin: Django formsets
    Our own modified version of `django-formset-js`_ is available as an independent
    django app and installed via pip.

.. _django-formset-js: https://github.com/tixl/django-formset-js
