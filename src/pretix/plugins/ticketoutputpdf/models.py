import string

from django.db import models
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _

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
        default='''[{
        "type":"textarea",
        "left":"17.50",
        "bottom":"274.60",
        "fontsize":"16.0",
        "color":[
            0,
            0,
            0,
            1
        ],
        "fontfamily":"Open Sans",
        "bold":false,
        "italic":false,
        "width":"175.00",
        "content":"event_name",
        "text":"Sample event name",
        "align":"left"
    },
    {
        "type":"textarea",
        "left":"17.50",
        "bottom":"262.90",
        "fontsize":"13.0",
        "color":[
            0,
            0,
            0,
            1
        ],
        "fontfamily":"Open Sans",
        "bold":false,
        "italic":false,
        "width":"110.00",
        "content":"itemvar",
        "text":"Sample product – sample variation",
        "align":"left"
    },
    {
        "type":"textarea",
        "left":"17.50",
        "bottom":"252.50",
        "fontsize":"13.0",
        "color":[
            0,
            0,
            0,
            1
        ],
        "fontfamily":"Open Sans",
        "bold":false,
        "italic":false,
        "width":"110.00",
        "content":"attendee_name",
        "text":"John Doe",
        "align":"left"
    },
    {
        "type":"textarea",
        "left":"17.50",
        "bottom":"242.10",
        "fontsize":"13.0",
        "color":[
            0,
            0,
            0,
            1
        ],
        "fontfamily":"Open Sans",
        "bold":false,
        "italic":false,
        "width":"110.00",
        "content":"event_date_range",
        "text":"May 31st – June 4th, 2017",
        "align":"left"
    },
    {
        "type":"textarea",
        "left":"17.50",
        "bottom":"231.70",
        "fontsize":"13.0",
        "color":[
            0,
            0,
            0,
            1
        ],
        "fontfamily":"Open Sans",
        "bold":false,
        "italic":false,
        "width":"110.00",
        "content":"seat",
        "text":"Ground floor, Row 3, Seat 4",
        "align":"left"
    },
    {
        "type":"textarea",
        "left":"17.50",
        "bottom":"204.80",
        "fontsize":"13.0",
        "color":[
            0,
            0,
            0,
            1
        ],
        "fontfamily":"Open Sans",
        "bold":false,
        "italic":false,
        "width":"110.00",
        "content":"event_location",
        "text":"Random City",
        "align":"left"
    },
    {
        "type":"textarea",
        "left":"17.50",
        "bottom":"194.50",
        "fontsize":"13.0",
        "color":[
            0,
            0,
            0,
            1
        ],
        "fontfamily":"Open Sans",
        "bold":false,
        "italic":false,
        "width":"30.00",
        "content":"order",
        "text":"A1B2C",
        "align":"left"
    },
    {
        "type":"textarea",
        "left":"52.50",
        "bottom":"194.50",
        "fontsize":"13.0",
        "color":[
            0,
            0,
            0,
            1
        ],
        "fontfamily":"Open Sans",
        "bold":false,
        "italic":false,
        "width":"45.00",
        "content":"price",
        "text":"123.45 EUR",
        "align":"right"
    },
    {
        "type":"textarea",
        "left":"102.50",
        "bottom":"194.50",
        "fontsize":"13.0",
        "color":[
            0,
            0,
            0,
            1
        ],
        "fontfamily":"Open Sans",
        "bold":false,
        "italic":false,
        "width":"90.00",
        "content":"secret",
        "text":"tdmruoekvkpbv1o2mv8xccvqcikvr58u",
        "align":"left"
    },
    {
        "type":"barcodearea",
        "left":"130.40",
        "bottom":"204.50",
        "size":"64.00"
    },
    {
        "type":"poweredby",
        "left":"88.72",
        "bottom":"10.00",
        "size":"20.00",
        "content":"dark"
    }]'''
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
        ordering = ("id",)
