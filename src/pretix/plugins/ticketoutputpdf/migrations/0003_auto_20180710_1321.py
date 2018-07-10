# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json

from django.db import migrations
from django.db.models import Q


def add_pretix_logo(app, schema_editor):
    TicketLayout = app.get_model('ticketoutputpdf', 'TicketLayout')
    for tl in TicketLayout.objects.filter(Q(background__isnull=True) | Q(background="")):
        l = json.loads(tl.layout)
        l.append({"type": "poweredby", "left": "88.72", "bottom": "10.00", "size": "20.00", "content": "dark"})
        tl.layout = json.dumps(l)
        tl.save(update_fields=['layout'])


class Migration(migrations.Migration):
    dependencies = [
        ('ticketoutputpdf', '0002_auto_20180605_2022'),
    ]

    operations = [
        migrations.RunPython(add_pretix_logo, migrations.RunPython.noop)
    ]
