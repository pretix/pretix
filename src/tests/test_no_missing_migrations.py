from io import StringIO

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_no_pending_migrations():
    out = StringIO()
    try:
        call_command(
            "makemigrations",
            "--check",
            stdout=out,
            stderr=StringIO(),
        )
    except SystemExit:  # pragma: no cover
        raise AssertionError("Pending migrations:\n" + out.getvalue()) from None
