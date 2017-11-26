from django.db import models
from django.utils.timezone import now
from django.utils.translation import pgettext_lazy, ugettext_lazy as _

from pretix.base.models import LoggedModel


class CheckinList(LoggedModel):
    event = models.ForeignKey('Event', related_name='checkin_lists')
    name = models.CharField(max_length=190)
    all_products = models.BooleanField(default=True, verbose_name=_("All products (including newly created ones)"))
    limit_products = models.ManyToManyField('Item', verbose_name=_("Limit to products"), blank=True)
    subevent = models.ForeignKey('SubEvent', null=True, blank=True,
                                 verbose_name=pgettext_lazy('subevent', 'Date'))


class Checkin(models.Model):
    """
    A checkin object is created when a person enters the event.
    """
    position = models.ForeignKey('pretixbase.OrderPosition', related_name='checkins')
    datetime = models.DateTimeField(default=now)
    nonce = models.CharField(max_length=190, null=True, blank=True)
    list = models.ForeignKey(
        'pretixbase.CheckinList', related_name='checkins', on_delete=models.PROTECT,
    )
