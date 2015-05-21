# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import pretix.base.models
import versions.models


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
                ('version_end_date', models.DateTimeField(blank=True, null=True, default=None)),
                ('version_birth_date', models.DateTimeField()),
                ('timeframe_from', models.DateTimeField(verbose_name='Start of time frame')),
                ('timeframe_to', models.DateTimeField(verbose_name='End of time frame')),
                ('price', models.DecimalField(max_digits=7, verbose_name='Price in time frame', decimal_places=2, null=True, blank=True)),
                ('event', versions.models.VersionedForeignKey(to='pretixbase.Event', related_name='restrictions_timerestriction_timerestriction', verbose_name='Event')),
                ('item', versions.models.VersionedForeignKey(to='pretixbase.Item', related_name='restrictions_timerestriction_timerestriction', verbose_name='Item', null=True, blank=True)),
                ('variations', pretix.base.models.VariationsField(related_name='restrictions_timerestriction_timerestriction', to='pretixbase.ItemVariation', verbose_name='Variations', blank=True)),
            ],
            options={
                'verbose_name_plural': 'Restrictions',
                'verbose_name': 'Restriction',
                'abstract': False,
            },
        ),
    ]
