# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0007_auto_20150212_0939'),
    ]

    operations = [
        migrations.AddField(
            model_name='quota',
            name='locked',
            field=models.DateTimeField(null=True, blank=True),
            preserve_default=True,
        ),
    ]
