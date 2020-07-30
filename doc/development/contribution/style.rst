Coding style and quality
========================

* Basically, we want all python code to follow the `PEP 8`_ standard. There are a few exceptions where
  we see things differently or just aren't that strict. The ``setup.cfg`` file in the project's source
  folder contains definitions that allow `flake8`_ to check for violations automatically. See :ref:`checksandtests`
  for more information. Use four spaces for indentation.

* We sort our imports by a certain schema, but you don't have to do this by hand. Again, ``setup.cfg`` contains
  some definitions that allow the command ``isort <directory>`` to automatically sort the imports in your source
  files.

* For templates and models, please take a look at the `Django Coding Style`_. We like Django's `class-based views`_ and
  kindly ask you to use them where appropriate.

* Please remember to always mark all strings ever displayed to any user for `translation`_.

* We expect all new code to come with proper tests. When writing new tests, please write them using `pytest-style`_
  test functions and raw ``assert`` statements. Use `fixtures`_ to prevent repetitive code. Some old parts of pretix'
  test suite are in the style of Python's unit test module. If you extend those files, you might continue in this style,
  but please use ``pytest`` style for any new test files.

* Please keep the first line of your commit messages short. When referencing an issue, please phrase it like
  ``Fix #123 -- Problems with order creation`` or ``Refs #123 -- Fix this part of that bug``.


.. _PEP 8: https://legacy.python.org/dev/peps/pep-0008/
.. _flake8: https://pypi.python.org/pypi/flake8
.. _Django Coding Style: https://docs.djangoproject.com/en/dev/internals/contributing/writing-code/coding-style/
.. _translation: https://docs.djangoproject.com/en/1.11/topics/i18n/translation/
.. _class-based views: https://docs.djangoproject.com/en/1.11/topics/class-based-views/
.. _pytest-style: https://docs.pytest.org/en/latest/assert.html
.. _fixtures: https://docs.pytest.org/en/latest/fixture.html
