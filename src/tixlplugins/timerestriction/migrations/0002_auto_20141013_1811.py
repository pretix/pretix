# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tixlbase', '0016_event_plugins'),
        ('timerestriction', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='timerestriction',
            name='items',
        ),
        migrations.AddField(
            model_name='timerestriction',
            name='i',
            field=models.ForeignKey(null=True, blank=True, related_name='restrictions_timerestriction_timerestriction', to='tixlbase.Item'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='timerestriction',
            name='variations',
            field=models.ManyToManyField(blank=True, related_name='restrictions_timerestriction_timerestriction', to='tixlbase.ItemVariation'),
        ),
    ]
