# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tixlbase', '0015_auto_20141006_2205'),
    ]

    operations = [
        migrations.CreateModel(
            name='TimeRestriction',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False, verbose_name='ID', auto_created=True)),
                ('timeframe_from', models.DateTimeField(verbose_name='Start of time frame')),
                ('timeframe_to', models.DateTimeField(verbose_name='End of time frame')),
                ('price', models.DecimalField(max_digits=7, verbose_name='Price in time frame', decimal_places=2, null=True, blank=True)),
                ('event', models.ForeignKey(related_name='restrictions_timerestriction_timerestriction', to='tixlbase.Event', verbose_name='Event')),
                ('items', models.ManyToManyField(to='tixlbase.Item', related_name='restrictions_timerestriction_timerestriction')),
                ('variations', models.ManyToManyField(to='tixlbase.ItemVariation', related_name='restrictions_timerestriction_timerestriction')),
            ],
            options={
                'abstract': False,
                'verbose_name_plural': 'Restrictions',
                'verbose_name': 'Restriction',
            },
            bases=(models.Model,),
        ),
    ]
