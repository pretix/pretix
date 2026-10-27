import logging

from django.db import transaction
from rest_framework.response import Response
from rest_framework.views import APIView

from pretix.helpers.database import OF_SELF
from pretix.plugins.wallet.models import GoogleWalletInstance
from pretix.plugins.wallet.styles.google_wallet import (
    GooglePaySignatureManager, Resource,
)

logger = logging.getLogger("pretix.plugins.wallet.google")


class CallbackView(APIView):
    authentication_classes = ()
    permission_classes = ()

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        webhook_json = GooglePaySignatureManager(
            request.event.settings.wallet_google_issuer_id
        ).unseal(request.data)

        object = (
            GoogleWalletInstance.objects.select_for_update(of=OF_SELF)
            .filter(
                resource=Resource.EVENT_TICKET_OBJECT,
                identifier=webhook_json["objectId"],
            )
            .first()
        )
        if object:
            if webhook_json["eventType"] == "save":
                object.usages += 1
            elif webhook_json["eventType"] == "del":
                object.usages -= 1
            object.save()

        return Response({})
