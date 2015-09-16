# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0013_auto_20150916_0941'),
    ]

    operations = [
        migrations.CreateModel(
            name='EventLock',
            fields=[
                ('event', models.CharField(primary_key=True, max_length=36, serialize=False)),
                ('date', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.RemoveField(
            model_name='quota',
            name='locked',
        ),
    ]
