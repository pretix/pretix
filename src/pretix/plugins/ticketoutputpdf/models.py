import string

from django.db import models
from django.utils.crypto import get_random_string
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import LoggedModel


def bg_name(instance, filename: str) -> str:
    secret = get_random_string(length=16, allowed_chars=string.ascii_letters + string.digits)
    return 'pub/{org}/{ev}/ticketoutputpdf/{id}-{secret}.pdf'.format(
        org=instance.event.organizer.slug,
        ev=instance.event.slug,
        id=instance.pk,
        secret=secret
    )


class TicketLayout(LoggedModel):
    event = models.ForeignKey(
        'pretixbase.Event',
        on_delete=models.CASCADE,
        related_name='ticket_layouts'
    )
    default = models.BooleanField(
        verbose_name=_('Default'),
        default=False,
    )
    name = models.CharField(
        max_length=190,
        verbose_name=_('Name')
    )
    layout = models.TextField(
        default='[{"italic": false, "bottom": "274.60", "align": "left", "fontfamily": "Open Sans", '
                '"width": "175.00", "left": "17.50", "text": "Sample event name", "content": "event_name", '
                '"fontsize": "16.0", "bold": false, "color": [0, 0, 0, 1], "type": "textarea"}, {"italic": false, '
                '"bottom": "262.90", "align": "left", "fontfamily": "Open Sans", "width": "110.00", "left": "17.50", '
                '"text": "Sample product \\u2013 sample variation", "content": "itemvar", "fontsize": "13.0", '
                '"bold": false, "color": [0, 0, 0, 1], "type": "textarea"}, {"italic": false, "bottom": "252.50", '
                '"align": "left", "fontfamily": "Open Sans", "width": "110.00", "left": "17.50", "text": "John Doe", '
                '"content": "attendee_name", "fontsize": "13.0", "bold": false, "color": [0, 0, 0, 1], '
                '"type": "textarea"}, {"italic": false, "bottom": "242.10", "align": "left", "fontfamily": "Open '
                'Sans", "width": "110.00", "left": "17.50", "text": "May 31st, 2017", "content": "event_date_range", '
                '"fontsize": "13.0", "bold": false, "color": [0, 0, 0, 1], "type": "textarea"}, {"italic": false, '
                '"bottom": "204.80", "align": "left", "fontfamily": "Open Sans", "width": "110.00", "left": "17.50", '
                '"text": "Random City", "content": "event_location", "fontsize": "13.0", "bold": false, "color": [0, '
                '0, 0, 1], "type": "textarea"}, {"italic": false, "bottom": "194.50", "align": "left", "fontfamily": '
                '"Open Sans", "width": "30.00", "left": "17.50", "text": "A1B2C", "content": "order", "fontsize": '
                '"13.0", "bold": false, "color": [0, 0, 0, 1], "type": "textarea"}, {"italic": false, '
                '"bottom": "194.50", "align": "right", "fontfamily": "Open Sans", "width": "45.00", "left": "52.50", '
                '"text": "123.45 EUR", "content": "price", "fontsize": "13.0", "bold": false, "color": [0, 0, 0, 1], '
                '"type": "textarea"}, {"italic": false, "bottom": "194.50", "align": "left", "fontfamily": "Open '
                'Sans", "width": "90.00", "left": "102.50", "text": "tdmruoekvkpbv1o2mv8xccvqcikvr58u", "content": '
                '"secret", "fontsize": "13.0", "bold": false, "color": [0, 0, 0, 1], "type": "textarea"}, '
                '{"left": "130.40", "bottom": "204.50", "type": "barcodearea", "size": "64.00"},{"type":"poweredby",'
                '"left":"88.72","bottom":"10.00","size":"20.00","content":"dark"}]'
    )
    background = models.FileField(null=True, blank=True, upload_to=bg_name, max_length=255)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class TicketLayoutItem(models.Model):
    item = models.ForeignKey('pretixbase.Item', null=True, blank=True, related_name='ticketlayout_assignments',
                             on_delete=models.CASCADE)
    layout = models.ForeignKey('TicketLayout', on_delete=models.CASCADE, related_name='item_assignments')
    sales_channel = models.CharField(max_length=190, default='web')

    class Meta:
        unique_together = (('item', 'layout', 'sales_channel'),)
