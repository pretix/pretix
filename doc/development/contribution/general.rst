Contribution workflow
=====================

You are interested in contributing to pretix? That is awesome!

If you’re new to contributing to open source software, don’t be afraid. We’ll happily review your code and give you
constructive and friendly feedback on your changes. Every contribution should go through the following steps.

Discussion & Design
-------------------

pretix is a large and mature project with more of a decade of history and hopefully many more decades to come.
Keeping pretix in good shape over long timeframes is first and foremost a fight against complexity.
With every additional feature, complexity grows, and both features and complexity are hard to remove.

Even if you are doing the initial work of the contribution, accepting the contribution is not free for us.
Not only will we need to maintain the feature, but every feature adds cost to the maintenance of every other feature it interacts with, and every feature adds effort for users to understand how pretix works.
Therefore, we must carefully select what features we add, based on how well they fit the system in general and of how much use they will be to our larger user base.

We strongly ask you to **create a discussion on GitHub for every new feature idea** outlining the use case and the proposed implementation design.
Pull requests without prior discussion will likely just be closed.

For bug fixes and very minor changes, you can skip this step and open a PR right away.

Development
-----------

To develop your contribution, you'll need pretix running locally on your machine. Head over to :ref:`devsetup` to learn how to do this.
If you run into any problems on your way, please do not hesitate to ask us anytime!

While developing, please have a look at our :ref:`aipolicy` and our guidelines on :ref:`codestyle`.

Sending a patch
---------------

Once you have a first draft of your changes, please `create a pull request`_ on our `GitHub repository`_.

We recommend that you create a feature branch for every issue you work on so the changes can
be reviewed individually.
Please use the test suite to check whether your changes break any existing features and run
the code style checks to confirm you are consistent with pretix's coding style. You'll
find instructions on this in the :ref:`checksandtests` section of the development setup guide.

We automatically run the tests and the code style check on every pull request through GitHub Actions and we won’t
accept any pull requests without all tests passing. However, if you don't find out *why* they are not passing,
just send the pull request and tell us – we'll be glad to help.

If you add a new feature, please include appropriate documentation into your patch. If you fix a bug,
please include a regression test, i.e. a test that fails without your changes and passes after applying your changes.

Again: If you get stuck, do not hesitate to contact us through GitHub discussions.

Please note that we bound ourselves to a :ref:`coc` that applies to all communication around the project. You can be
assured that we will not tolerate any form of harassment.

.. _create a pull request: https://help.github.com/articles/creating-a-pull-request/
.. _GitHub repository: https://github.com/pretix/pretix
