# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0014_auto_20150305_2310'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='payment_provider',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='Payment provider'),
        ),
        migrations.AlterField(
            model_name='order',
            name='datetime',
            field=models.DateTimeField(verbose_name='Date'),
        ),
    ]
