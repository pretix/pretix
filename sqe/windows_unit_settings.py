"""Run the upstream pytest settings with Windows-safe logging cleanup."""

import atexit
import logging

from tests.settings import *  # NOQA

# Windows does not let TemporaryDirectory remove files held by FileHandlers.
# Close the logs before pretix's previously registered temp-directory cleanup.
atexit.register(logging.shutdown)
