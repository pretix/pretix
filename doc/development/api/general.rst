.. highlight:: python
   :linenothreshold: 5

General APIs
============

This page lists some general signals and hooks which do not belong to a
specific type of plugin but might come in handy for various plugins.

HTML head injection
-------------------

These two signals allow you to put code inside the HTML ``<head>`` tag
of every page. One signal is for the frontend, one for the backend. You
will get the request as a keyword argument ``request`` and can return plain
HTML.

* ``pretix.presale.signals.html_head``
* ``pretix.control.signals.html_head``