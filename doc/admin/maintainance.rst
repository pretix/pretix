.. highlight:: ini

.. _`maintainance`:

Backups and Monitoring
======================

If you host your own pretix instance, you also need to care about the availability
of your service and the safety of your data yourself. This page gives you some
information that you might need to do so properly.

Backups
-------

There are essentially two things which you should create backups of:

Database
    Your SQL database (MySQL or PostgreSQL). This is critical and you should **absolutely
    always create automatic backups of your database**. There are tons of tutorials on the
    internet on how to do this, and the exact process depends on the choice of your database.
    For MySQL, see ``mysqldump`` and for PostgreSQL, see the ``pg_dump`` tool. You probably
    want to create a cronjob that does the backups for you on a regular schedule.

Data directory
    The data directory of your pretix configuration might contain some things that you should
    back up. If you did not specify a secret in your config file, back up the ``.secret`` text
    file in the data directory. If you lose your secret, all currently active user sessions,
    password reset links and similar things will be rendered invalid. Also, you probably want
    to backup the ``media`` subdirectory of the data directory which contains all user-uploaded
    and generated files. This includes files you could in theory regenerate (ticket downloads)
    but also files that you might be legally required to keep (invoice PDFs) or files that you
    would need to re-upload (event logos, product pictures, etc.). It is up to you if you
    create regular backups of this data, but we strongly advise you to do so. You can create
    backups e.g. using ``rsync``. There is a lot of information on the internet on how to create
    backups of folders on a Linux machine.

There is no need to create backups of the redis database, if you use it. We only use it for
non-critical, temporary or cached data.

Uptime monitoring
-----------------

To monitor whether your pretix instance is running, you can issue a GET request to
``https://pretix.mydomain.com/healthcheck/``. This endpoint tests if the connection to the
database, to the configured cache and to redis (if used) is working correctly. If everything
appears to work fine, an empty response with status code ``200`` is returned.
If there is a problem, a status code in the ``5xx`` range will be returned.

.. _`perf-monitoring`:

Performance monitoring
----------------------

If you want to generate detailed performance statistics of your pretix installation, there is an
endpoint at ``https://pretix.mydomain.com/metrics`` (no slash at the end) which returns a
number of values in the text format understood by monitoring tools like Prometheus_. This data
is only collected and exposed if you enable it in the :ref:`metrics-settings` section of your
pretix configuration. You can also configure basic auth credentials there to protect your
statistics against unauthorized access. The data is temporarily collected in redis, so the
performance impact of this feature depends on the connection to your redis database.

Currently, mostly response times of HTTP requests and background tasks are exposed.

If you want to go even further, you can set the ``profile`` option in the :ref:`django-settings`
section to a value between 0 and 1. If you set it for example to 0.1, then 10% of your requests
(randomly selected) will be run with cProfile_ activated. The profiling results will be saved
to your data directory. As this might impact performance significantly and writes a lot of data
to disk, we recommend to only enable it for a small number of requests -- and only if you are
really interested in the results.

Available metrics
^^^^^^^^^^^^^^^^^

The metrics available in pretix follow the standard `metric types`_ from the Prometheus world.
Currently, the following metrics are exported:

pretix_view_requests_total
    Counter. Counts requests to Django views, labeled with the resolved ``url_name``, the used
    HTTP ``method`` and the ``status_code`` returned.

pretix_view_durations_seconds
    Histogram. Measures duration of requests to Django views, labeled with the resolved
    ``url_name``, the used HTTP ``method`` and the ``status_code`` returned.

pretix_task_runs_total
    Counter. Counts executions of background tasks, labeled with the ``task_name`` and the
    ``status``. The latter can be ``success``, ``error`` or ``expected-error``.

pretix_task_duration_seconds
    Histogram. Measures duration of successful background task executions, labeled with the
    ``task_name``.

pretix_model_instances
    Gauge. Measures number of instances of a certain model within the database, labeled with
    the ``model`` name. Starting with pretix 3.11, these numbers might only be approximate for
    most tables when running on PostgreSQL to mitigate performance impact.

pretix_celery_tasks_queued_count
    The number of background tasks in the worker queue, labeled with ``queue``.

pretix_celery_tasks_queued_age_seconds
    The age of the longest-waiting in the worker queue in seconds, labeled with ``queue``.

.. _metric types: https://prometheus.io/docs/concepts/metric_types/
.. _Prometheus: https://prometheus.io/
.. _cProfile: https://docs.python.org/3/library/profile.html
