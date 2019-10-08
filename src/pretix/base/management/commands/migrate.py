"""
Django tries to be helpful by suggesting to run "makemigrations" in red font on every "migrate"
run when there are things we have no migrations for. Usually, this is intended, and running
"makemigrations" can really screw up the environment of a user, so we want to prevent novice
users from doing that by going really dirty and filtering it from the output.
"""
import sys

from django.core.management.base import OutputWrapper
from django.core.management.commands.migrate import Command as Parent


class OutputFilter(OutputWrapper):
    banlist = (
        "Your models have changes that are not yet reflected",
        "Run 'manage.py makemigrations' to make new "
    )

    def write(self, msg, style_func=None, ending=None):
        if any(b in msg for b in self.banlist):
            return
        super().write(msg, style_func, ending)


class Command(Parent):
    def __init__(self, stdout=None, stderr=None, no_color=False, force_color=False):
        super().__init__(stdout, stderr, no_color, force_color)
        self.stdout = OutputFilter(stdout or sys.stdout)
