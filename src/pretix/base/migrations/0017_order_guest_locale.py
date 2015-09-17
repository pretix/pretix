# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0016_order_guest_email'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='guest_locale',
            field=models.CharField(max_length=32, null=True, blank=True, verbose_name='Locale'),
        ),
    ]
