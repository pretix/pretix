.. spelling:word-list:: Rebase rebasing

Coding style and quality
========================

Code
----

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

Commits and Pull Requests
-------------------------



Most commits should start as pull requests, therefore this applies to the titles of pull requests as well since
the pull request title will become the commit message on merge. We prefer merging with GitHub's "Squash and merge"
feature if the PR contains multiple commits that do not carry value to keep. If there is value in keeping the
individual commits, we use "Rebase and merge" instead. Merge commits should be avoided.

* The commit message should start with a single subject line and can optionally be followed by a commit message body.

  * The subject line should be the shortest possible representation of what the commit changes. Someone who reviewed
    the commit should able to immediately remember the commit in a couple of weeks based on the subject line and tell
    it apart from other commits.

  * If there's additional useful information that we should keep, such as reasoning behind the commit, you can
    add a longer body, separated from the first line by a blank line.

  * The body should explain **what** you changed and more importantly **why** you changed it. There's no need to iterate
    **how** you changed something.

* The subject line should be capitalized ("Add new feature" instead of "add new feature") and should not end with a period
  ("Add new feature" instead of "Add new feature.")

* The subject line should be written in imperative mood, as if you were giving a command what the computer should do if the
  commit is applied. This is how generated commit messages by git itself are already written ("Merge branch …", "Revert …")
  and makes for short and consistent messages.

  * Good: "Fix typo in template"
  * Good: "Add Chinese translation"
  * Good: "Remove deprecated method"
  * Good: "Bump version to 4.4.0"
  * Bad: "Fixed bug with …"
  * Bad: "Fixes bug with …"
  * Bad: "Fixing bug …"

* If all changes in your commit are in context of a single feature or e.g. a bundled plugin, it makes sense to prefix the
  subject line with the name of that feature. Examples:

  * "API: Add support for PATCH on customers"
  * "Docs: Add chapter on alpaca feeding"
  * "Stripe: Fix duplicate payments"
  * "Order change form: Fix incorrect validation"

* If your commit references a GitHub issue that is fully resolved by your commit, start your subject line with the issue
  ID in the form of "Fix #1234 -- Crash in order list". In this case, you can omit the verb "Fix" at the beginning of the
  second part of the message to avoid repetition of the word "fix". If your commit only partially resolves the issue, use
  "Refs #1234 -- Crash in order list" instead.

* Applies to pretix employees only: If your commit references a sentry issue, please put it in parentheses at the end
  of the subject line or inside the body ("Fix crash in order list (PRETIXEU-ABC)"). If your commit references a support
  ticket, please put it in parentheses at the end of the subject line with a "Z#" prefix ("Fix crash in order list (Z#12345)").

* If your PR was open for a while and might cause conflicts on merge, please prefer rebasing it (``git rebase -i master``)
  over merging ``master`` into your branch unless it is prohibitively complicated.


.. _PEP 8: https://legacy.python.org/dev/peps/pep-0008/
.. _flake8: https://pypi.python.org/pypi/flake8
.. _Django Coding Style: https://docs.djangoproject.com/en/dev/internals/contributing/writing-code/coding-style/
.. _translation: https://docs.djangoproject.com/en/1.11/topics/i18n/translation/
.. _class-based views: https://docs.djangoproject.com/en/1.11/topics/class-based-views/
.. _pytest-style: https://docs.pytest.org/en/latest/assert.html
.. _fixtures: https://docs.pytest.org/en/latest/fixture.html
