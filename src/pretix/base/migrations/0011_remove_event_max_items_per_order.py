# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0010_auto_20150218_2048'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='event',
            name='max_items_per_order',
        ),
    ]
