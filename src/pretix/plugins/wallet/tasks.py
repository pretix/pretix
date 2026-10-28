from pretix.base.services.tasks import EventTask
from pretix.celery_app import app



@app.task(base=EventTask)
def refresh_passes(event, op_ids):
    pass

@app.task(base=EventTask)
def cleanup_passes(event):
    # TODO: clean old wallet objects
    # * GoogleWalletInstance.objects.filter(usages=0, updated_at__lt=now() - timedelta(hours=2))
    # * everything for events that have ended X time ago(?)
    # * anonymize tickets when event is shredded
    pass