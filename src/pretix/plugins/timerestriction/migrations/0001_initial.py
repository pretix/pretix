# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import versions.models
from django.db import migrations, models

import pretix.base.models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '__first__'),
    ]

    operations = [
        migrations.CreateModel(
            name='TimeRestriction',
            fields=[
                ('id', models.CharField(serialize=False, max_length=36, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(null=True, blank=True, default=None)),
                ('version_birth_date', models.DateTimeField()),
                ('timeframe_from', models.DateTimeField(verbose_name='Start of time frame')),
                ('timeframe_to', models.DateTimeField(verbose_name='End of time frame')),
                ('price', models.DecimalField(decimal_places=2, max_digits=7, null=True, blank=True, verbose_name='Price in time frame')),
                ('event', versions.models.VersionedForeignKey(verbose_name='Event', to='pretixbase.Event', related_name='restrictions_timerestriction_timerestriction')),
                ('item', versions.models.VersionedForeignKey(related_name='restrictions_timerestriction_timerestriction', null=True, verbose_name='Item', to='pretixbase.Item', blank=True)),
                ('variations', pretix.base.models.VariationsField(related_name='restrictions_timerestriction_timerestriction', blank=True, to='pretixbase.ItemVariation', verbose_name='Variations')),
            ],
            options={
                'verbose_name_plural': 'Restrictions',
                'abstract': False,
                'verbose_name': 'Restriction',
            },
        ),
    ]
