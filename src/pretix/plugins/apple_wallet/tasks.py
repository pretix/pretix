from pretix.base.models import Event
from pretix.celery_app import app
import ssl
import httpx
import tempfile
from django.utils.timezone import now
from django.db.models import OuterRef, Exists

from .models import AppleWalletPass, AppleWalletDevice
from django_scopes import scopes_disabled


@app.task
@scopes_disabled()
def send_update_apns():
    events_to_push = Event.objects.filter(
        plugins__icontains="pretix.plugins.apple_wallet"
    ).filter(
        Exists(
            AppleWalletDevice.objects.filter(
                Exists(
                    AppleWalletPass.objects.filter(
                        registered_devices=OuterRef("pk"),
                        updated_at__gte=OuterRef("last_push"),
                        order_position__order__event=OuterRef(OuterRef("pk")),
                    )
                )
            )
        )
    )

    for event in events_to_push:
        devices_to_push = AppleWalletDevice.objects.filter(
            Exists(
                AppleWalletPass.objects.filter(
                    registered_devices=OuterRef("pk"),
                    updated_at__gte=OuterRef("last_push"),
                    order_position__order__event=event,
                )
            )
        )
        if not devices_to_push.exists():
            return

        ca_cert = event.settings.wallet_apple_certificate.read()
        cert = event.settings.wallet_apple_certificate.read()
        key = event.settings.wallet_apple_key.read()

        ctx = ssl.create_default_context()

        with tempfile.NamedTemporaryFile("w") as certfile:
            certfile.write(key)
            certfile.write("\n")
            certfile.write(cert)
            certfile.write("\n")
            certfile.write(ca_cert)
            certfile.flush()
            ctx.load_cert_chain(
                certfile=certfile.name,
                password=event.settings.wallet_apple_key_password,
            )

        client = httpx.Client(verify=ctx, http1=False, http2=True)

        for device in devices_to_push:
            device.last_push = now()
            client.post(
                f"https://api.push.apple.com/3/device/{device.push_token}", json={}
            )
            device.save()
