from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_scopes import ScopedManager
from jsonfallback.fields import FallbackJSONField
from phonenumber_field.modelfields import PhoneNumberField

from pretix.base.email import get_email_context
from pretix.base.i18n import language
from pretix.base.models import Voucher
from pretix.base.services.mail import mail
from pretix.base.settings import PERSON_NAME_SCHEMES

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
    name_cached = models.CharField(
        max_length=255,
        verbose_name=_("Name"),
        blank=True, null=True,
    )
    name_parts = FallbackJSONField(
        blank=True, default=dict
    )
    email = models.EmailField(
        verbose_name=_("E-mail address")
    )
    phone = PhoneNumberField(
        null=True, blank=True,
        verbose_name=_("Phone number")
    )
    voucher = models.ForeignKey(
        'Voucher',
        verbose_name=_("Assigned voucher"),
        null=True, blank=True,
        related_name='waitinglistentries',
        on_delete=models.CASCADE
    )
    item = models.ForeignKey(
        Item, related_name='waitinglistentries', on_delete=models.CASCADE,
        verbose_name=_("Product"),
        help_text=_(
            "The product the user waits for."
        )
    )
    variation = models.ForeignKey(
        ItemVariation, related_name='waitinglistentries',
        null=True, blank=True, on_delete=models.CASCADE,
        verbose_name=_("Product variation"),
        help_text=_(
            "The variation of the product selected above."
        )
    )
    locale = models.CharField(
        max_length=190,
        default='en'
    )
    priority = models.IntegerField(default=0)

    objects = ScopedManager(organizer='event__organizer')

    class Meta:
        verbose_name = _("Waiting list entry")
        verbose_name_plural = _("Waiting list entries")
        ordering = ('-priority', 'created')

    def __str__(self):
        return '%s waits for %s' % (str(self.email), str(self.item))

    def clean(self):
        WaitingListEntry.clean_duplicate(self.email, self.item, self.variation, self.subevent, self.pk)
        WaitingListEntry.clean_itemvar(self.event, self.item, self.variation)
        WaitingListEntry.clean_subevent(self.event, self.subevent)

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields', [])
        if 'name_parts' in update_fields:
            update_fields.append('name_cached')
        self.name_cached = self.name
        if self.name_parts is None:
            self.name_parts = {}
        super().save(*args, **kwargs)

    @property
    def name(self):
        if not self.name_parts:
            return None
        if '_legacy' in self.name_parts:
            return self.name_parts['_legacy']
        if '_scheme' in self.name_parts:
            scheme = PERSON_NAME_SCHEMES[self.name_parts['_scheme']]
        else:
            scheme = PERSON_NAME_SCHEMES[self.event.settings.name_scheme]
        return scheme['concatenation'](self.name_parts).strip()

    def send_voucher(self, quota_cache=None, user=None, auth=None):
        availability = (
            self.variation.check_quotas(count_waitinglist=False, subevent=self.subevent, _cache=quota_cache)
            if self.variation
            else self.item.check_quotas(count_waitinglist=False, subevent=self.subevent, _cache=quota_cache)
        )
        if availability[1] is None or availability[1] < 1:
            raise WaitingListException(_('This product is currently not available.'))
        if self.voucher:
            raise WaitingListException(_('A voucher has already been sent to this person.'))
        if '@' not in self.email:
            raise WaitingListException(_('This entry is anonymized and can no longer be used.'))

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
            }, user=user, auth=auth)
            self.log_action('pretix.waitinglist.voucher', user=user, auth=auth)
            self.voucher = v
            self.save()

        with language(self.locale, self.event.settings.region):
            mail(
                self.email,
                _('You have been selected from the waitinglist for {event}').format(event=str(self.event)),
                self.event.settings.mail_text_waiting_list,
                get_email_context(event=self.event, waiting_list_entry=self),
                self.event,
                locale=self.locale
            )

    @staticmethod
    def clean_itemvar(event, item, variation):
        if event != item.event:
            raise ValidationError(_('The selected item does not belong to this event.'))
        if item.has_variations and (not variation or variation.item != item):
            raise ValidationError(_('Please select a specific variation of this product.'))

    @staticmethod
    def clean_subevent(event, subevent):
        if event.has_subevents:
            if not subevent:
                raise ValidationError(_('Subevent cannot be null for event series.'))
            if event != subevent.event:
                raise ValidationError(_('The subevent does not belong to this event.'))
        else:
            if subevent:
                raise ValidationError(_('The subevent does not belong to this event.'))

    @staticmethod
    def clean_duplicate(email, item, variation, subevent, pk):
        if WaitingListEntry.objects.filter(
                item=item, variation=variation, email__iexact=email, voucher__isnull=True, subevent=subevent
        ).exclude(pk=pk).exists():
            raise ValidationError(_('You are already on this waiting list! We will notify '
                                    'you as soon as we have a ticket available for you.'))
