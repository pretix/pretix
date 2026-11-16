from pretix.celery_app import app
from .google_wallet import (
    Resource, State,
)
from .platform import GooglePlatform

from .models import GoogleWalletInstance


@app.task()
def disable_wallet_instance(pk: int):
    try:
        obj = GoogleWalletInstance.objects.get(pk=pk)
    except GoogleWalletInstance.DoesNotExist:
        return

    platform = GooglePlatform(obj.event)
    platform.comms.patch_item(Resource(obj.resource), obj.identifier, {"state": State.INACTIVE})
    obj.delete()
