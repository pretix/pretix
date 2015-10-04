# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import versions.models
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0012_remove_order_tickets'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cachedticket',
            name='order',
            field=versions.models.VersionedForeignKey(to='pretixbase.Order'),
        ),
    ]
