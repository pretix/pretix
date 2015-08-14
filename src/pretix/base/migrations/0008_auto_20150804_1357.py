# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0007_auto_20150726_1430'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='order',
            options={'verbose_name_plural': 'Orders', 'verbose_name': 'Order', 'ordering': ('-datetime',)},
        ),
        migrations.AlterField(
            model_name='item',
            name='default_price',
            field=models.DecimalField(max_digits=7, decimal_places=2, verbose_name='Default price', null=True),
        ),
    ]
