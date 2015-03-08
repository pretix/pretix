# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0015_auto_20150308_0953'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='code',
            field=models.CharField(max_length=16, verbose_name='Order code', default=''),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='order',
            name='payment_fee',
            field=models.DecimalField(max_digits=10, verbose_name='Payment method fee', decimal_places=2, default=0),
            preserve_default=False,
        ),
    ]
