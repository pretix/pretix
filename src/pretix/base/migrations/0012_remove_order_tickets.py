# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0011_auto_20150915_2020'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='order',
            name='tickets',
        ),
    ]
