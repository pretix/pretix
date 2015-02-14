# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import pretix.base.models
import versions.models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0004_auto_20150211_2330'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='payment_date',
            field=models.DateTimeField(null=True, blank=True, verbose_name='Payment date'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='order',
            name='payment_info',
            field=models.TextField(null=True, blank=True, verbose_name='Payment information'),
            preserve_default=True,
        ),
    ]
