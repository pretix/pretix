from django.http import HttpResponseNotImplemented
from django.views import View


class RunLotteryView(View):
    """Run the waiting-list lottery for a product. Implemented in Phase 2."""

    def get(self, request, *args, **kwargs):
        return HttpResponseNotImplemented(
            "Sideburn lottery run is not implemented yet."
        )


class RevertLotteryView(View):
    """Revert a waiting-list lottery run for a product. Implemented in Phase 2."""

    def get(self, request, *args, **kwargs):
        return HttpResponseNotImplemented(
            "Sideburn lottery revert is not implemented yet."
        )
