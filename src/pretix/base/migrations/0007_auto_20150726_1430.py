# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0006_auto_20150726_1420'),
    ]

    operations = [
        migrations.AlterField(
            model_name='item',
            name='default_price',
            field=models.DecimalField(verbose_name='Default price', default=0, decimal_places=2, max_digits=7),
            preserve_default=False,
        ),
    ]
