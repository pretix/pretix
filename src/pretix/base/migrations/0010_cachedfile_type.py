# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0009_auto_20150915_2003'),
    ]

    operations = [
        migrations.AddField(
            model_name='cachedfile',
            name='type',
            field=models.CharField(default='text/plain', max_length=255),
            preserve_default=False,
        ),
    ]
