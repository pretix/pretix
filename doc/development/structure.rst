Project structure
=================

Python source code
------------------

All the source code lives in ``src/``, which has several subdirectories.

pretix/
    This directory contains the basic Django settings and URL routing.

pretixbase/
    This is the django app containing all the models and methods which are
    essential to all of pretix's features.

pretixcontrol/
    This is the django app containing the frontend for organizers.

pretixpresale/
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

pretixcontrol
    pretixcontrol has two main LESS files, ``pretixcontrol/static/pretixcontrol/less/main.less`` and
    ``pretixcontrol/static/pretixcontrol/less/auth.less``, importing everything else.

3rd-party assets
^^^^^^^^^^^^^^^^

Bootstrap
    Bootstrap lives as a git submodule at ``pretixbase/static/bootstrap/``

Font Awesome
    Font Awesome lives as a git submodule at ``pretixbase/static/fontawesome/``

jQuery
    jQuery lives as a single JavaScript file in ``pretixbase/static/jquery/js/``

jQuery plugin: Django formsets
    Our own modified version of `django-formset-js`_ is available as an independent
    django app and installed via pip.

.. _django-formset-js: https://github.com/pretix/django-formset-js
