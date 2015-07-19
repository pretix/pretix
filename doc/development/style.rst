Coding style
============

Python code
-----------

* Basically: Follow `PEP 8`_.

  Use `flake8`_ to check for conformance problems. The project includes a setup.cfg
  with a default configuration for flake8 that excludes migrations and other non-relevant
  code parts. It also silences a few checks, e.g. ``N802`` (function names should be lowercase) 
  and increases the maximum line length to more than 79 characters. **However** you should 
  still name all your functions lowercase [#f1]_ and keep your lines short when possible.

* Our build server will reject all code violating other flake8 checks than the following:
  
  * E123: closing bracket does not match indentation of opening bracket’s line
  * F403: ``from module import *`` used; unable to detect undefined names
  * F401: module imported but unused
  * N802: function names should be lowercase

 So please make sure that you *always* follow all other rules and break these rules *only when
 it makes sense*.

* Use ``isort -rc pretix`` in the source directory to order your imports.

* Indent your code with four spaces.

* For templates and models, follow the `Django Coding Style`_.

* Use Django's class-based views

* Always mark all strings ever displayed to any user for translation.

LESS stylesheets
----------------

* Indent your code with four spaces.
* Make use of the nesting feature of LESS to put your code in logical groups, but avoid using 
  more than three levels of nesting.
* Put spaces after ``:`` in declarations.
* Put spaces before ``{`` in rulesets.
* When grouping selectors, use one line per selector.
* Place closing brackets on an own line.
* Use only one declaration per line.
* Use the `mixins`_ feature from LESS, especially when dealing with browser-specific statements
  like ``-webkit-transform``, ``-moz-transform``, etc.
* Use hex color codes (or ``rgba()``, if needed)
* Put colors into variables, if you use them more than once (and maybe even then)



.. _PEP 8: http://legacy.python.org/dev/peps/pep-0008/
.. _flake8: https://pypi.python.org/pypi/flake8
.. _Django Coding Style: https://docs.djangoproject.com/en/dev/internals/contributing/writing-code/coding-style/
.. _mixins: http://lesscss.org/features/#mixins-feature
.. [#f1] But Python's very own ``unittest`` module forces us to use ``setUp`` as a method name...
