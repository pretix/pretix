# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import versions.models
from django.db import migrations, models

import pretix.base.models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='TimeRestriction',
            fields=[
                ('id', models.CharField(primary_key=True, serialize=False, max_length=36)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('timeframe_from', models.DateTimeField(verbose_name='Start of time frame')),
                ('timeframe_to', models.DateTimeField(verbose_name='End of time frame')),
                ('price', models.DecimalField(verbose_name='Price in time frame', blank=True, max_digits=7, null=True, decimal_places=2)),
                ('event', versions.models.VersionedForeignKey(verbose_name='Event', related_name='restrictions_timerestriction_timerestriction', to='pretixbase.Event')),
                ('item', versions.models.VersionedForeignKey(verbose_name='Item', related_name='restrictions_timerestriction_timerestriction', to='pretixbase.Item', null=True, blank=True)),
                ('variations', pretix.base.models.VariationsField(verbose_name='Variations', blank=True, related_name='restrictions_timerestriction_timerestriction', to='pretixbase.ItemVariation')),
            ],
            options={
                'verbose_name_plural': 'Restrictions',
                'verbose_name': 'Restriction',
                'abstract': False,
            },
        ),
    ]
