"""Settings for k6 performance runs: identical to the SQE Windows instance, but with DEBUG disabled.

DEBUG=True keeps every SQL query in memory and adds per-request overhead, which would distort latency.
The API endpoint measured by k6 does not need static files, so nothing else changes.
"""

from sqe.windows_settings import *  # NOQA

DEBUG = False
