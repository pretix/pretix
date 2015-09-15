# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0010_cachedfile_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cachedfile',
            name='id',
            field=models.UUIDField(serialize=False, primary_key=True, default=uuid.uuid4),
        ),
    ]
