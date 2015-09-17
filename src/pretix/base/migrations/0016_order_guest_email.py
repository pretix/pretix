# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0015_auto_20150916_2219'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='guest_email',
            field=models.EmailField(max_length=254, verbose_name='E-mail', blank=True, null=True),
        ),
    ]
