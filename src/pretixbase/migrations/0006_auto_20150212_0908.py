# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import pretixbase.models
import versions.models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0005_auto_20150212_0901'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cartposition',
            name='datetime',
            field=models.DateTimeField(auto_now_add=True, verbose_name='Date'),
            preserve_default=True,
        ),
    ]
