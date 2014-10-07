# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tixlbase', '0015_auto_20141006_2205'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='plugins',
            field=models.TextField(blank=True, verbose_name='Plugins', null=True),
            preserve_default=True,
        ),
    ]
