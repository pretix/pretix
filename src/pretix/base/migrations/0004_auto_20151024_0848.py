# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0003_event_is_public'),
    ]

    operations = [
        migrations.RenameField(
            model_name='cartposition',
            old_name='session',
            new_name='cart_id'
        ),
        migrations.AlterField(
            model_name='cartposition',
            name='cart_id',
            field=models.CharField(blank=True, verbose_name='Cart ID (e.g. session key)', max_length=255, null=True),
        ),
    ]
