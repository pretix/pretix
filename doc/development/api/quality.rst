.. highlight:: python
   :linenothreshold: 5

.. _`pluginquality`:

Plugin quality checklist
========================

If you want to write a high-quality pretix plugin, this is a list of things you should check before
you publish it. This is also a list of things that we check, if we consider installing an externally
developed plugin on our hosted infrastructure.

A. Meta
-------

#. The plugin is clearly licensed under an appropriate license.

#. The plugin has an unambiguous name, description, and author metadata.

#. The plugin has a clear versioning scheme and the latest version of the plugin is kept compatible to the latest
   stable version of pretix.

#. The plugin is properly packaged using standard Python packaging tools.

#. The plugin correctly declares its external dependencies.

#. A contact address is provided in case of security issues.

B. Isolation
------------

#. If any signal receivers use the `dispatch_uid`_ feature, the UIDs are prefixed by the plugin's name and do not
   clash with other plugins.

#. If any templates or static files are shipped, they are located in subdirectories with the name of the plugin and do
   not clash with other plugins or core files.

#. Any keys stored to the settings store are prefixed with the plugin's name and do not clash with other plugins or
   core.

#. Any keys stored to the user session are prefixed with the plugin's name and do not clash with other plugins or
   core.

#. Any registered URLs are unlikely to clash with other plugins or future core URLs.

C. Security
-----------

#. All important actions are logged to the :ref:`shared log storage <logging>` and a signal receiver is registered to
   provide a human-readable representation of the log entry.

#. All views require appropriate permissions and use the ``event_urls`` mechanism if appropriate.
   :ref:`Read more <customview>`

#. Any session data for customers is stored in the cart session system if appropriate.

#. If the plugin is a payment provider:

  #. No credit card numbers may be stored within pretix.

  #. A notification/webhook system is implemented to notify pretix of any refunds.

  #. If such a webhook system is implemented, contents of incoming webhooks are either verified using a cryptographic
     signature or are not being trusted and all data is fetched from an API instead.

D. Privacy
----------

#. No personal data is stored that is not required for the plugin's functionality.

#. For any personal data that is saved to the database, an appropriate :ref:`data shredder <shredder>` is provided
   that offers the data for download and then removes it from the database (including log entries).

E. Internationalization
-----------------------

#. All user-facing strings in templates, Python code, and templates are wrapped in `gettext calls`_.

#. No languages, time zones, date formats, or time formats are hardcoded.

#. Installing the plugin automatically compiles ``.po`` files to ``.mo`` files. This is fulfilled automatically if
   you use the ``setup.py`` file form our plugin cookiecutter.

F. Functionality
----------------

#. If the plugin adds any database models or relationships from the settings storage to database models, it registers
   a receiver to the :py:attr:`pretix.base.signals.event_copy_data` or :py:attr:`pretix.base.signals.item_copy_data`
   signals.

#. If the plugin is a payment provider:

    #. A webhook-like system is implemented if payment confirmations are not sent instantly.

    #. Refunds are implemented, if possible.

    #. In case of overpayment or external refunds, an external refund is properly created.

#. If the plugin adds steps to the checkout process, it has been tested in combination with the pretix widget.

G. Code quality
---------------

#. `isort`_ and `flake8`_ are used to ensure consistent code styling.

#. Unit tests are provided for important pieces of business logic.

#. Functional tests are provided for important interface parts.

#. Tests are provided to check that permission checks are working.

#. Continuous Integration is set up to check that tests are passing and styling is consistent.

H. Specific to pretix.eu
------------------------

#. pretix.eu integrates the data stored by this plugin with its data report features.

#. pretix.eu integrates this plugin in its generated privacy statements, if necessary.


.. _isort: https://www.google.de/search?q=isort&oq=isort&aqs=chrome..69i57j0j69i59j69i60l2j69i59.599j0j4&sourceid=chrome&ie=UTF-8
.. _flake8: http://flake8.pycqa.org/en/latest/
.. _gettext calls: https://docs.djangoproject.com/en/2.0/topics/i18n/translation/
.. _dispatch_uid: https://docs.djangoproject.com/en/2.0/topics/signals/#django.dispatch.Signal.connect
