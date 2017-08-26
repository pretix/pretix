General remarks
===============

You are interested in contributing to pretix? That is awesome!

If you’re new to contributing to open source software, don’t be afraid. We’ll happily review your code and give you
constructive and friendly feedback on your changes.

First of all, you'll need pretix running locally on your machine. Head over to :ref:`devsetup` to learn how to do this.
If you run into any problems on your way, please do not hesitate to ask us anytime!

Please note that we bound ourselves to a :ref:`coc` that applies to all communication around the project. You can be
assured that we will not tolerate any form of harassment.

Sending a patch
---------------

If you improved pretix in any way, we'd be very happy if you contribute it
back to the main code base! The easiest way to do so is to `create a pull request`_
on our `GitHub repository`_.

We recommend that you create a feature branch for every issue you work on so the changes can
be reviewed individually.
Please use the test suite to check whether your changes break any existing features and run
the code style checks to confirm you are consistent with pretix's coding style. You'll
find instructions on this in the :ref:`checksandtests` section of the development setup guide.

We automatically run the tests and the code style check on every pull request on Travis CI and we won’t
accept any pull requests without all tests passing. However, if you don't find out *why* they are not passing,
just send the pull request and tell us – we'll be glad to help.

If you add a new feature, please include appropriate documentation into your patch. If you fix a bug,
please include a regression test, i.e. a test that fails without your changes and passes after applying your changes.

Again: If you get stuck, do not hesitate to contact any of us, or Raphael personally at mail@raphaelmichel.de.

.. _create a pull request: https://help.github.com/articles/creating-a-pull-request/
.. _GitHub repository: https://github.com/pretix/pretix
