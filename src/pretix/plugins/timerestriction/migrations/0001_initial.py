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
                ('id', models.CharField(serialize=False, primary_key=True, max_length=36)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(null=True, blank=True, default=None)),
                ('version_birth_date', models.DateTimeField()),
                ('timeframe_from', models.DateTimeField(verbose_name='Start of time frame')),
                ('timeframe_to', models.DateTimeField(verbose_name='End of time frame')),
                ('price', models.DecimalField(null=True, blank=True, verbose_name='Price in time frame', max_digits=7, decimal_places=2)),
                ('event', versions.models.VersionedForeignKey(to='pretixbase.Event', related_name='restrictions_timerestriction_timerestriction', verbose_name='Event')),
                ('item', versions.models.VersionedForeignKey(to='pretixbase.Item', blank=True, null=True, related_name='restrictions_timerestriction_timerestriction', verbose_name='Item')),
                ('variations', pretix.base.models.VariationsField(to='pretixbase.ItemVariation', blank=True,
                                                                  verbose_name='Variations', related_name='restrictions_timerestriction_timerestriction')),
            ],
            options={
                'verbose_name': 'Restriction',
                'verbose_name_plural': 'Restrictions',
                'abstract': False,
            },
            bases=(models.Model,),
        ),
    ]
