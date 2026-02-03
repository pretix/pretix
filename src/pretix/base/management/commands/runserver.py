# SPDX-FileCopyrightText: 2023-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

"""This command supersedes the Django-inbuilt runserver command.

It runs the local frontend server, if node is installed and the setting
is set.
"""
import os
import atexit
import subprocess
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles.management.commands.runserver import Command as Parent
from django.utils.autoreload import DJANGO_AUTORELOAD_ENV


class Command(Parent):
    def handle(self, *args, **options):
        # Only start Vite in the non-main process of the autoreloader
        if settings.VITE_DEV_MODE and os.environ.get(DJANGO_AUTORELOAD_ENV) != "true":
            # Start the vite server in the background
            vite_server = subprocess.Popen(
                ["npm", "run", "dev"],
                cwd=Path(__file__).parent.parent.parent.parent.parent
            )

            def cleanup():
                vite_server.terminate()
                try:
                    vite_server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    vite_server.kill()
            
            atexit.register(cleanup)

        super().handle(*args, **options)
