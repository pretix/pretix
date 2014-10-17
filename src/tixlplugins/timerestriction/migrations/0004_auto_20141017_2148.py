# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import tixlbase.models


class Migration(migrations.Migration):

    dependencies = [
        ('timerestriction', '0003_auto_20141013_1811'),
    ]

    operations = [
        migrations.AlterField(
            model_name='timerestriction',
            name='item',
            field=models.ForeignKey(null=True, blank=True, related_name='restrictions_timerestriction_timerestriction', to='tixlbase.Item', verbose_name='Item'),
        ),
        migrations.AlterField(
            model_name='timerestriction',
            name='variations',
            field=tixlbase.models.VariationsField(related_name='restrictions_timerestriction_timerestriction', to='tixlbase.ItemVariation', blank=True, verbose_name='Variations'),
        ),
    ]
