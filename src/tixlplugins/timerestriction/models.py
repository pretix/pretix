from django.db import models
from django.utils.translation import ugettext_lazy as _

from tixlbase.models import BaseRestriction


class TimeRestriction(BaseRestriction):
    """
    This restriction makes an item or variation only available
    within a given time frame. The price of the item can be modified
    during this time frame.
    """

    timeframe_from = models.DateTimeField(
        verbose_name=_("Start of time frame"),
    )
    timeframe_to = models.DateTimeField(
        verbose_name=_("End of time frame"),
    )
    price = models.DecimalField(
        null=True, blank=True,
        max_digits=7, decimal_places=2,
        verbose_name=_("Price in time frame"),
    )
