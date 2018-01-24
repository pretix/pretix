from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils.timezone import now
from django.utils.translation import pgettext_lazy, ugettext_lazy as _

from pretix.base.i18n import language
from pretix.base.models import Voucher
from pretix.base.services.mail import mail
from pretix.multidomain.urlreverse import build_absolute_uri

from .base import LoggedModel
from .event import Event, SubEvent
from .items import Item, ItemVariation


class WaitingListException(Exception):
    pass


class WaitingListEntry(LoggedModel):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="waitinglistentries",
        verbose_name=_("Event"),
    )
    subevent = models.ForeignKey(
        SubEvent,
        null=True, blank=True,
        on_delete=models.CASCADE,
        verbose_name=pgettext_lazy("subevent", "Date"),
    )
    created = models.DateTimeField(
        verbose_name=_("On waiting list since"),
        auto_now_add=True
    )
    email = models.EmailField(
        verbose_name=_("E-mail address")
    )
    voucher = models.ForeignKey(
        'Voucher',
        verbose_name=_("Assigned voucher"),
        null=True, blank=True
    )
    item = models.ForeignKey(
        Item, related_name='waitinglistentries',
        verbose_name=_("Product"),
        help_text=_(
            "The product the user waits for."
        )
    )
    variation = models.ForeignKey(
        ItemVariation, related_name='waitinglistentries',
        null=True, blank=True,
        verbose_name=_("Product variation"),
        help_text=_(
            "The variation of the product selected above."
        )
    )
    locale = models.CharField(
        max_length=190,
        default='en'
    )

    class Meta:
        verbose_name = _("Waiting list entry")
        verbose_name_plural = _("Waiting list entries")
        ordering = ['created']

    def __str__(self):
        return '%s waits for %s' % (str(self.email), str(self.item))

    def clean(self):
        if WaitingListEntry.objects.filter(
            item=self.item, variation=self.variation, email=self.email, voucher__isnull=True
        ).exclude(pk=self.pk).exists():
            raise ValidationError(_('You are already on this waiting list! We will notify '
                                    'you as soon as we have a ticket available for you.'))
        if not self.variation and self.item.has_variations:
            raise ValidationError(_('Please select a specific variation of this product.'))

    def send_voucher(self, quota_cache=None, user=None):
        availability = (
            self.variation.check_quotas(count_waitinglist=False, subevent=self.subevent, _cache=quota_cache)
            if self.variation
            else self.item.check_quotas(count_waitinglist=False, subevent=self.subevent, _cache=quota_cache)
        )
        if availability[1] is None or availability[1] < 1:
            raise WaitingListException(_('This product is currently not available.'))
        if self.voucher:
            raise WaitingListException(_('A voucher has already been sent to this person.'))

        with transaction.atomic():
            v = Voucher.objects.create(
                event=self.event,
                max_usages=1,
                valid_until=now() + timedelta(hours=self.event.settings.waiting_list_hours),
                item=self.item,
                variation=self.variation,
                tag='waiting-list',
                comment=_('Automatically created from waiting list entry for {email}').format(
                    email=self.email
                ),
                block_quota=True,
                subevent=self.subevent,
            )
            v.log_action('pretix.voucher.added.waitinglist', {
                'item': self.item.pk,
                'variation': self.variation.pk if self.variation else None,
                'tag': 'waiting-list',
                'block_quota': True,
                'valid_until': v.valid_until.isoformat(),
                'max_usages': 1,
                'email': self.email,
                'waitinglistentry': self.pk,
                'subevent': self.subevent.pk if self.subevent else None,
            }, user=user)
            self.log_action('pretix.waitinglist.voucher', user=user)
            self.voucher = v
            self.save()

        with language(self.locale):
            mail(
                self.email,
                _('You have been selected from the waitinglist for {event}').format(event=str(self.event)),
                self.event.settings.mail_text_waiting_list,
                {
                    'event': self.event.name,
                    'url': build_absolute_uri(self.event, 'presale:event.redeem') + '?voucher=' + self.voucher.code,
                    'code': self.voucher.code,
                    'product': str(self.item) + (' - ' + str(self.variation) if self.variation else ''),
                    'hours': self.event.settings.waiting_list_hours,
                },
                self.event,
                locale=self.locale
            )
