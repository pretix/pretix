import string

from django.db import models
from django.utils.crypto import get_random_string
from django.utils.translation import pgettext_lazy, ugettext_lazy as _


class AppConfiguration(models.Model):
    event = models.ForeignKey('pretixbase.Event')
    key = models.CharField(max_length=190, unique=True, db_index=True)
    all_items = models.BooleanField(default=True, verbose_name=_('Can scan all products'))
    items = models.ManyToManyField('pretixbase.Item', blank=True, verbose_name=_('Can scan these products'))
    subevent = models.ForeignKey('pretixbase.SubEvent', null=True, blank=True,
                                 verbose_name=pgettext_lazy('subevent', 'Date'))
    show_info = models.BooleanField(default=True, verbose_name=_('Show information'),
                                    help_text=_('If disabled, the device can not see how many tickets exist and how '
                                                'many are already scanned. pretixdroid 1.6 or newer only.'))
    allow_search = models.BooleanField(default=True, verbose_name=_('Search allowed'),
                                       help_text=_('If disabled, the device can not search for attendees by name. '
                                                   'pretixdroid 1.6 or newer only.'))

    def save(self, **kwargs):
        if not self.key:
            self.key = get_random_string(
                length=32, allowed_chars=string.ascii_uppercase + string.ascii_lowercase + string.digits
            )
        return super().save(**kwargs)
