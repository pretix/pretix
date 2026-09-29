import sys

from django.conf import settings

if sys.version_info < (3, 12):
    # due-work-harness needs Python 3.12 or later.
    collect_ignore_glob = ['*.py']
elif 'postgresql' not in settings.DATABASES['default']['ENGINE']:
    # Its probes read PostgreSQL's transaction state, so the contract runs on PostgreSQL only.
    collect_ignore_glob = ['*.py']
else:
    from due_work_harness import configure
    from due_work_harness.integrations.celery import celery_publication_breaker
    from due_work_harness.integrations.django import django_host
    from due_work_harness.integrations.django.receivers import (
        django_receiver_breaker,
    )

    from pretix.base.signals import order_paid, order_placed

    configure(
        django_host(
            production_packages={'pretix'},
            # A refused publish, as a broker that is down would; a failing plugin receiver.
            publication_breaker=celery_publication_breaker,
            receiver_breaker=django_receiver_breaker(order_placed, order_paid),
        )
    )
