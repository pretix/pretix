Project structure
=================

Python source code
------------------

All the source code lives in ``src/``, which has several subdirectories.

pretix/
    This directory contains nearly all source code.

    base/
        This is the Django app containing all the models and methods which are
        essential to all of pretix's features.

    control/
        This is the Django app containing the front end for organizers.

    presale/
        This is the Django app containing the front end for users buying tickets.

    helpers/
        Helpers contain a very few modules providing workarounds for low-level flaws in
        Django or installed 3rd-party packages.

    multidomain/
        Additional code implementing our customized :ref:`URL handling <urlconf>`.

    static/
        Contains all static files (CSS, JavaScript, images)

    static/
        Contains some pretix plugins that ship with pretix itself

tests/
    This is the root directory for all test codes. It includes subdirectories ``base``,
    ``control``, ``presale``, ``helpers`` and ``plugins`` to mirror the structure of the
    ``pretix`` source code as well as ``testdummy``, which is a pretix plugin used during
    testing.

Language files
--------------

The language files live in ``pretix/locale/*/LC_MESSAGES/``.

Static files
------------

Sass source code
^^^^^^^^^^^^^^^^

We use libsass as a preprocessor for CSS. Our own sass code is built in the same
step as Bootstrap and FontAwesome, so their mixins etc. are fully available.

pretix.control
    pretixcontrol has two main SCSS files, ``pretix/static/pretixcontrol/scss/main.scss`` and
    ``pretix/static/pretixcontrol/scss/auth.scss``, importing everything else.

pretix.presale
    pretixpresale has one main SCSS files, ``pretix/pretixpresale/scss/main.scss``,
    importing everything else.

3rd-party assets
^^^^^^^^^^^^^^^^

Most client-side 3rd-party assets are vendored in various subdirectories of ``pretix/static``.
