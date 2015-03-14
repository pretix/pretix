# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import versions.models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0017_auto_20150308_1507'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(verbose_name='Status', choices=[('p', 'pending'), ('n', 'paid'), ('e', 'expired'), ('c', 'cancelled'), ('r', 'refunded')], max_length=3),
        ),
        migrations.AlterField(
            model_name='orderposition',
            name='order',
            field=versions.models.VersionedForeignKey(verbose_name='Order', to='pretixbase.Order', related_name='positions'),
        ),
    ]
