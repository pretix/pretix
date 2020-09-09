import hashlib
import re

from django.db import models


class BankImportJob(models.Model):
    STATE_PENDING = 'pending'
    STATE_RUNNING = 'running'
    STATE_ERROR = 'error'
    STATE_COMPLETED = 'completed'
    STATES = (
        (STATE_PENDING, 'pending'),
        (STATE_RUNNING, 'running'),
        (STATE_ERROR, 'error'),
        (STATE_COMPLETED, 'completed'),
    )

    event = models.ForeignKey('pretixbase.Event', null=True, on_delete=models.CASCADE)
    organizer = models.ForeignKey('pretixbase.Organizer', null=True, on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)
    state = models.CharField(max_length=32, choices=STATES, default=STATE_PENDING)

    class Meta:
        ordering = ('id',)

    @property
    def owner_kwargs(self):
        if self.event:
            return {'event': self.event}
        else:
            return {'organizer': self.organizer}


class BankTransaction(models.Model):
    STATE_UNCHECKED = 'imported'
    STATE_NOMATCH = 'nomatch'
    STATE_INVALID = 'invalid'
    STATE_ERROR = 'error'
    STATE_VALID = 'valid'
    STATE_DISCARDED = 'discarded'
    STATE_DUPLICATE = 'already'

    STATES = (
        (STATE_UNCHECKED, 'imported, unchecked'),
        (STATE_NOMATCH, 'no match'),
        (STATE_INVALID, 'not valid'),
        (STATE_ERROR, 'error'),
        (STATE_VALID, 'valid'),
        (STATE_DUPLICATE, 'valid, already paid'),
        (STATE_DISCARDED, 'manually discarded'),
    )

    event = models.ForeignKey('pretixbase.Event', null=True, on_delete=models.CASCADE)
    organizer = models.ForeignKey('pretixbase.Organizer', null=True, on_delete=models.CASCADE)
    import_job = models.ForeignKey('BankImportJob', related_name='transactions', on_delete=models.CASCADE)
    state = models.CharField(max_length=32, choices=STATES, default=STATE_UNCHECKED)
    message = models.TextField()
    checksum = models.CharField(max_length=190, db_index=True)
    payer = models.TextField(blank=True)
    reference = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.CharField(max_length=50)
    date_parsed = models.DateField(null=True)
    iban = models.CharField(max_length=250, blank=True)
    bic = models.CharField(max_length=250, blank=True)
    order = models.ForeignKey('pretixbase.Order', null=True, blank=True, on_delete=models.CASCADE)
    comment = models.TextField(blank=True)

    def calculate_checksum(self):
        clean = re.compile('[^a-zA-Z0-9.-]')
        hasher = hashlib.sha1()
        hasher.update(clean.sub('', self.payer.lower()).encode('utf-8'))
        hasher.update(clean.sub('', self.reference.lower()).encode('utf-8'))
        hasher.update(clean.sub('', str(self.amount).lower()).encode('utf-8'))
        hasher.update(clean.sub('', self.date.lower()).encode('utf-8'))
        return str(hasher.hexdigest())

    def shred_private_data(self):
        self.payer = ""
        self.reference = ""

    class Meta:
        unique_together = ('event', 'organizer', 'checksum')
        ordering = ('date', 'id')


class RefundExport(models.Model):
    event = models.ForeignKey('pretixbase.Event', related_name='banktransfer_refund_exports', on_delete=models.CASCADE, null=True, blank=True)
    organizer = models.ForeignKey('pretixbase.Organizer', related_name='banktransfer_refund_exports', on_delete=models.PROTECT, null=True, blank=True)
    datetime = models.DateTimeField(auto_now_add=True)
    testmode = models.BooleanField(default=False)
    rows = models.TextField(default="[]")


class BankTransferRefund(models.Model):
    export = models.ForeignKey(RefundExport, on_delete=models.CASCADE)
    order = models.ForeignKey('pretixbase.Order', on_delete=models.CASCADE)
    refund = models.ForeignKey('pretixbase.OrderRefund', on_delete=models.CASCADE, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
