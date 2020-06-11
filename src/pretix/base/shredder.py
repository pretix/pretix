import json
from datetime import timedelta
from typing import List, Tuple

from django.db import transaction
from django.db.models import Max, Q
from django.db.models.functions import Greatest
from django.dispatch import receiver
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

from pretix.api.serializers.order import (
    AnswerSerializer, InvoiceAddressSerializer,
)
from pretix.api.serializers.waitinglist import WaitingListSerializer
from pretix.base.i18n import LazyLocaleException
from pretix.base.models import (
    CachedCombinedTicket, CachedTicket, Event, InvoiceAddress, OrderPayment,
    OrderPosition, OrderRefund, QuestionAnswer,
)
from pretix.base.services.invoices import invoice_pdf_task
from pretix.base.signals import register_data_shredders


class ShredError(LazyLocaleException):
    pass


def shred_constraints(event: Event):
    if event.has_subevents:
        max_date = event.subevents.aggregate(
            max_from=Max('date_from'),
            max_to=Max('date_to'),
            max_fromto=Greatest(Max('date_to'), Max('date_from'))
        )
        max_date = max_date['max_fromto'] or max_date['max_to'] or max_date['max_from']
        if max_date is not None and max_date > now() - timedelta(days=30):
            return _('Your event needs to be over for at least 30 days to use this feature.')
    else:
        if (event.date_to or event.date_from) > now() - timedelta(days=30):
            return _('Your event needs to be over for at least 30 days to use this feature.')
    if event.live:
        return _('Your ticket shop needs to be offline to use this feature.')
    return None


class BaseDataShredder:
    """
    This is the base class for all data shredders.
    """

    def __init__(self, event: Event):
        self.event = event

    def __str__(self):
        return self.identifier

    def generate_files(self) -> List[Tuple[str, str, str]]:
        """
        This method is called to export the data that is about to be shred and return a list of tuples consisting of a
        filename, a file type and file content.

        You can also implement this as a generator and ``yield`` those tuples instead of returning a list of them.
        """
        raise NotImplementedError()  # NOQA

    def shred_data(self):
        """
        This method is called to actually remove the data from the system. You should remove any database objects
        here.

        You should never delete ``LogEntry`` objects, but you might modify them to remove personal data. In this
        case, set the ``LogEntry.shredded`` attribute to ``True`` to show that this is no longer original log data.
        """
        raise NotImplementedError()  # NOQA

    @property
    def tax_relevant(self):
        """
        Indicates whether this removes potentially tax-relevant data.
        """
        return False

    @property
    def verbose_name(self) -> str:
        """
        A human-readable name for what this shredder removes. This should be short but self-explanatory.
        Good examples include 'E-Mail addresses' or 'Invoices'.
        """
        raise NotImplementedError()  # NOQA

    @property
    def identifier(self) -> str:
        """
        A short and unique identifier for this shredder.
        This should only contain lowercase letters and in most
        cases will be the same as your package name.
        """
        raise NotImplementedError()  # NOQA

    @property
    def description(self) -> str:
        """
        A more detailed description of what this shredder does. Can contain HTML.
        """
        raise NotImplementedError()  # NOQA


def shred_log_fields(logentry, banlist=None, whitelist=None):
    d = logentry.parsed_data
    if whitelist:
        for k, v in d.items():
            if k not in whitelist:
                d[k] = '█'
    elif banlist:
        for f in banlist:
            if f in d:
                d[f] = '█'
    logentry.data = json.dumps(d)
    logentry.shredded = True
    logentry.save(update_fields=['data', 'shredded'])


class EmailAddressShredder(BaseDataShredder):
    verbose_name = _('E-mails')
    identifier = 'order_emails'
    description = _('This will remove all e-mail addresses from orders and attendees, as well as logged email '
                    'contents.')

    def generate_files(self) -> List[Tuple[str, str, str]]:
        yield 'emails-by-order.json', 'application/json', json.dumps({
            o.code: o.email for o in self.event.orders.filter(email__isnull=False)
        }, indent=4)
        yield 'emails-by-attendee.json', 'application/json', json.dumps({
            '{}-{}'.format(op.order.code, op.positionid): op.attendee_email
            for op in OrderPosition.all.filter(order__event=self.event, attendee_email__isnull=False)
        }, indent=4)

    @transaction.atomic
    def shred_data(self):
        OrderPosition.all.filter(order__event=self.event, attendee_email__isnull=False).update(attendee_email=None)

        for o in self.event.orders.all():
            o.email = None
            d = o.meta_info_data
            if d:
                if 'contact_form_data' in d and 'email' in d['contact_form_data']:
                    del d['contact_form_data']['email']
                o.meta_info = json.dumps(d)
            o.save(update_fields=['meta_info', 'email'])

        for le in self.event.logentry_set.filter(action_type__contains="order.email"):
            shred_log_fields(le, banlist=['recipient', 'message', 'subject'])

        for le in self.event.logentry_set.filter(action_type="pretix.event.order.contact.changed"):
            shred_log_fields(le, banlist=['old_email', 'new_email'])

        for le in self.event.logentry_set.filter(action_type="pretix.event.order.modified").exclude(data=""):
            d = le.parsed_data
            if 'data' in d:
                for row in d['data']:
                    if 'attendee_email' in row:
                        row['attendee_email'] = '█'
                le.data = json.dumps(d)
                le.shredded = True
                le.save(update_fields=['data', 'shredded'])


class WaitingListShredder(BaseDataShredder):
    verbose_name = _('Waiting list')
    identifier = 'waiting_list'
    description = _('This will remove all email addresses from the waiting list.')

    def generate_files(self) -> List[Tuple[str, str, str]]:
        yield 'waiting-list.json', 'application/json', json.dumps([
            WaitingListSerializer(wle).data
            for wle in self.event.waitinglistentries.all()
        ], indent=4)

    @transaction.atomic
    def shred_data(self):
        self.event.waitinglistentries.update(email='█')

        for wle in self.event.waitinglistentries.select_related('voucher').filter(voucher__isnull=False):
            if '@' in wle.voucher.comment:
                wle.voucher.comment = '█'
                wle.voucher.save(update_fields=['comment'])

        for le in self.event.logentry_set.filter(action_type="pretix.voucher.added.waitinglist").exclude(data=""):
            d = le.parsed_data
            d['email'] = '█'
            le.data = json.dumps(d)
            le.shredded = True
            le.save(update_fields=['data', 'shredded'])


class AttendeeInfoShredder(BaseDataShredder):
    verbose_name = _('Attendee info')
    identifier = 'attendee_info'
    description = _('This will remove all attendee names and postal addresses from order positions, as well as logged '
                    'changes to them.')

    def generate_files(self) -> List[Tuple[str, str, str]]:
        yield 'attendee-info.json', 'application/json', json.dumps({
            '{}-{}'.format(op.order.code, op.positionid): {
                'name': op.attendee_name,
                'company': op.company,
                'street': op.street,
                'zipcode': op.zipcode,
                'city': op.city,
                'country': str(op.country) if op.country else None,
                'state': op.state
            } for op in OrderPosition.all.filter(
                order__event=self.event
            ).filter(
                Q(Q(attendee_name_cached__isnull=False) | Q(attendee_name_parts__isnull=False))
            )
        }, indent=4)

    @transaction.atomic
    def shred_data(self):
        OrderPosition.all.filter(
            order__event=self.event
        ).filter(
            Q(attendee_name_cached__isnull=False) | Q(attendee_name_parts__isnull=False) |
            Q(company__isnull=False) | Q(street__isnull=False) | Q(zipcode__isnull=False) | Q(city__isnull=False)
        ).update(attendee_name_cached=None, attendee_name_parts={'_shredded': True}, company=None, street=None,
                 zipcode=None, city=None)

        for le in self.event.logentry_set.filter(action_type="pretix.event.order.modified").exclude(data=""):
            d = le.parsed_data
            if 'data' in d:
                for i, row in enumerate(d['data']):
                    if 'attendee_name' in row:
                        d['data'][i]['attendee_name'] = '█'
                    if 'attendee_name_parts' in row:
                        d['data'][i]['attendee_name_parts'] = {
                            '_legacy': '█'
                        }
                if 'company' in row:
                    d['data'][i]['company'] = '█'
                if 'street' in row:
                    d['data'][i]['street'] = '█'
                if 'zipcode' in row:
                    d['data'][i]['zipcode'] = '█'
                if 'city' in row:
                    d['data'][i]['city'] = '█'
                le.data = json.dumps(d)
                le.shredded = True
                le.save(update_fields=['data', 'shredded'])


class InvoiceAddressShredder(BaseDataShredder):
    verbose_name = _('Invoice addresses')
    identifier = 'invoice_addresses'
    tax_relevant = True
    description = _('This will remove all invoice addresses from orders, as well as logged changes to them.')

    def generate_files(self) -> List[Tuple[str, str, str]]:
        yield 'invoice-addresses.json', 'application/json', json.dumps({
            ia.order.code: InvoiceAddressSerializer(ia).data
            for ia in InvoiceAddress.objects.filter(order__event=self.event)
        }, indent=4)

    @transaction.atomic
    def shred_data(self):
        InvoiceAddress.objects.filter(order__event=self.event).delete()

        for le in self.event.logentry_set.filter(action_type="pretix.event.order.modified").exclude(data=""):
            d = le.parsed_data
            if 'invoice_data' in d and not isinstance(d['invoice_data'], bool):
                for field in d['invoice_data']:
                    if d['invoice_data'][field]:
                        d['invoice_data'][field] = '█'
                le.data = json.dumps(d)
                le.shredded = True
                le.save(update_fields=['data', 'shredded'])


class QuestionAnswerShredder(BaseDataShredder):
    verbose_name = _('Question answers')
    identifier = 'question_answers'
    description = _('This will remove all answers to questions, as well as logged changes to them.')

    def generate_files(self) -> List[Tuple[str, str, str]]:
        yield 'question-answers.json', 'application/json', json.dumps({
            '{}-{}'.format(op.order.code, op.positionid): AnswerSerializer(op.answers.all(), many=True).data
            for op in OrderPosition.all.filter(order__event=self.event).prefetch_related('answers')
        }, indent=4)

    @transaction.atomic
    def shred_data(self):
        QuestionAnswer.objects.filter(orderposition__order__event=self.event).delete()

        for le in self.event.logentry_set.filter(action_type="pretix.event.order.modified").exclude(data=""):
            d = le.parsed_data
            if 'data' in d:
                for i, row in enumerate(d['data']):
                    for f in row:
                        if f not in ('attendee_name', 'attendee_email'):
                            d['data'][i][f] = '█'
                le.data = json.dumps(d)
                le.shredded = True
                le.save(update_fields=['data', 'shredded'])


class InvoiceShredder(BaseDataShredder):
    verbose_name = _('Invoices')
    identifier = 'invoices'
    tax_relevant = True
    description = _('This will remove all invoice PDFs, as well as any of their text content that might contain '
                    'personal data from the database. Invoice numbers and totals will be conserved.')

    def generate_files(self) -> List[Tuple[str, str, str]]:
        for i in self.event.invoices.filter(shredded=False):
            if not i.file:
                invoice_pdf_task.apply(args=(i.pk,))
                i.refresh_from_db()
            i.file.open('rb')
            yield 'invoices/{}.pdf'.format(i.number), 'application/pdf', i.file.read()
            i.file.close()

    @transaction.atomic
    def shred_data(self):
        for i in self.event.invoices.filter(shredded=False):
            if i.file:
                i.file.delete()
                i.shredded = True
                i.introductory_text = "█"
                i.additional_text = "█"
                i.invoice_to = "█"
                i.payment_provider_text = "█"
                i.save()
                i.lines.update(description="█")


class CachedTicketShredder(BaseDataShredder):
    verbose_name = _('Cached ticket files')
    identifier = 'cachedtickets'
    description = _('This will remove all cached ticket files. No download will be offered.')

    def generate_files(self) -> List[Tuple[str, str, str]]:
        pass

    @transaction.atomic
    def shred_data(self):
        CachedTicket.objects.filter(order_position__order__event=self.event).delete()
        CachedCombinedTicket.objects.filter(order__event=self.event).delete()


class PaymentInfoShredder(BaseDataShredder):
    verbose_name = _('Payment information')
    identifier = 'payment_info'
    tax_relevant = True
    description = _('This will remove payment-related information. Depending on the payment method, all data will be '
                    'removed or personal data only. No download will be offered.')

    def generate_files(self) -> List[Tuple[str, str, str]]:
        pass

    @transaction.atomic
    def shred_data(self):
        provs = self.event.get_payment_providers()
        for obj in OrderPayment.objects.filter(order__event=self.event):
            pprov = provs.get(obj.provider)
            if pprov:
                pprov.shred_payment_info(obj)
        for obj in OrderRefund.objects.filter(order__event=self.event):
            pprov = provs.get(obj.provider)
            if pprov:
                pprov.shred_payment_info(obj)


@receiver(register_data_shredders, dispatch_uid="shredders_builtin")
def register_payment_provider(sender, **kwargs):
    return [
        EmailAddressShredder,
        AttendeeInfoShredder,
        InvoiceAddressShredder,
        QuestionAnswerShredder,
        InvoiceShredder,
        CachedTicketShredder,
        PaymentInfoShredder,
        WaitingListShredder
    ]
