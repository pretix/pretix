# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import versions.models
import pretix.base.models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0002_auto_20150211_2031'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='quota',
            name='lock_cache',
        ),
        migrations.RemoveField(
            model_name='quota',
            name='order_cache',
        ),
    ]
