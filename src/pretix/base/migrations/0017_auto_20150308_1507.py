# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0016_auto_20150308_1017'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='payment_fee',
            field=models.DecimalField(verbose_name='Payment method fee', default=0, max_digits=10, decimal_places=2),
        ),
    ]
