# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import versions.models
import pretix.base.models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0006_auto_20150212_0908'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='max_items_per_order',
            field=models.IntegerField(verbose_name='Maximum number of items per order', default=10),
            preserve_default=True,
        ),
    ]
