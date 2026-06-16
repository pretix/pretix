from django.http import HttpResponse
from django.views import View


class RunLotteryView(View):
    """Run the waiting-list lottery for a product. Implemented in Phase 2."""

    def get(self, request, *args, **kwargs):
        return HttpResponse(
            "Sideburn lottery run is not implemented yet.",
            status=501,
        )


class RevertLotteryView(View):
    """Revert a waiting-list lottery run for a product. Implemented in Phase 2."""

    def get(self, request, *args, **kwargs):
        return HttpResponse(
            "Sideburn lottery revert is not implemented yet.",
            status=501,
        )
