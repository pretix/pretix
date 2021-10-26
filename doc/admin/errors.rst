.. _`admin-errors`:

Dealing with errors
===================

If you encounter an error in pretix, please follow the following steps to debug it:

* If the error message is shown on a **white page** and the last line of the error includes "nginx", the error is not with pretix
  directly but with your nginx webserver. This might mean that pretix is not running, but it could also be something else.
  Please first check your nginx error log. The default location is ``/var/log/nginx/error.log``.

  * If it turns out pretix is not running, check the output of ``docker logs pretix`` for a docker installation and
    ``journalctl -u pretix-web.service`` for a manual installation.

* If the error message is an "**Internal Server Error**" in purple pretix design, please check pretix' log file which by default is at
  ``/var/pretix-data/logs/pretix.log`` if you installed with docker and ``/var/pretix/data/logs/pretix.log`` otherwise. If you don't
  know how to interpret it, open a discussion on GitHub with the relevant parts of the log file.

  * If the error message includes ``/usr/bin/env: ‘node’: No such file or directory``, you forgot to install ``node.js``

  * If the error message includes ``OfflineGenerationError``, you might have forgot to run the ``rebuild`` step after a pretix update
    or plugin installation.

  * If the error message mentions your database server or redis server, make sure these are running and accessible.

* If pretix loads fine but certain actions (creating carts, orders, or exports, downloading tickets, sending emails) **take forever**,
  ``pretix-worker`` is not running. Check the output of ``docker logs pretix`` for a docker installation and
  ``journalctl -u pretix-worker.service`` for a manual installation.

* If the page loads but all **styles are missing**, you probably forgot to update your nginx configuration file after an upgrade of your
  operating system's python version.


If you are unable to debug the issue any further, please open a **discussion** on GitHub in our `Q&A Forum`_. Do **not** open an issue
right away, since most things turn out not to be a bug in pretix but a mistake in your server configuration. Make sure to include
relevant log excerpts in your question.

If you're a pretix Enterprise customer, you can also reach out to support@pretix.eu with your issue right away.

.. _Q&A Forum: https://github.com/pretix/pretix/discussions/categories/q-a
