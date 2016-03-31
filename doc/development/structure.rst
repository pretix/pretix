Project structure
=================

Python source code
------------------

All the source code lives in ``src/``, which has several subdirectories.

pretix/
    This directory contains nearly all source code.

    base/
        This is the django app containing all the models and methods which are
        essential to all of pretix's features.

    control/
        This is the django app containing the front end for organizers.

    presale/
        This is the django app containing the front end for users buying tickets.

    helpers/
        Helpers contain a very few modules providing workarounds for low-level flaws in
        Django or installed 3rd-party packages, like a filter to combine the ``lessc``
        preprocessor with ``django-compressor``'s URL rewriting.

static/
    Contains all static files (CSS, JavaScript, images)

tests/
    This is the root directory for all test codes. It includes subdirectories ``base``,
    ``control``, ``presale``, ``helpers`` and ``plugins`` to mirror the structure of the
    ``pretix`` source code as well as ``testdummy``, which is a pretix plugin used during
    testing.

Language files
--------------
The language files live in ``locale/*/LC_MESSAGES/``.

Static files
------------

Sass source code
^^^^^^^^^^^^^^^^

We use libsass as a preprocessor for CSS. Our own sass code is built in the same
step as Bootstrap and FontAwesome, so their mixins etc. are fully available.

pretix.control
    pretixcontrol has two main SCSS files, ``pretix/control/static/pretixcontrol/scss/main.scss`` and
    ``pretix/control/static/pretixcontrol/scss/auth.scss``, importing everything else.

pretix.presale
    pretixpresale has one main SCSS files, ``pretix/control/static/pretix/presale/scss/main.scss``,
    importing everything else.

3rd-party assets
^^^^^^^^^^^^^^^^

Bootstrap
    Bootstrap lives vendored at ``static/bootstrap/``

Font Awesome
    Font Awesome lives vendored at ``static/fontawesome/``

jQuery
    jQuery lives as a single JavaScript file in ``static/jquery/js/``

jQuery plugin: Django formsets
    Our own modified version of `django-formset-js`_ is available as an independent
    django app and installed via pip.

.. _django-formset-js: https://github.com/pretix/django-formset-js
