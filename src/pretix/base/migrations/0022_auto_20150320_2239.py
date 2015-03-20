# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0021_auto_20150320_1622'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='payment_manual',
            field=models.BooleanField(verbose_name='Payment state was manually modified', default=False),
        ),
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(verbose_name='Status', max_length=3, choices=[('n', 'pending'), ('p', 'paid'), ('e', 'expired'), ('c', 'cancelled'), ('r', 'refunded')]),
        ),
    ]
