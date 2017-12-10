from pretix.base.models import LogEntry
from pretix.base.services.async import TransactionAwareTask
from pretix.celery_app import app


@app.task(base=TransactionAwareTask)
def notify(logentry_id: int):
    logentry = LogEntry.objects.get(id=logentry_id)
    logentry.pk
