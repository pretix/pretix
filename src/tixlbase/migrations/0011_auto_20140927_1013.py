# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tixlbase', '0010_auto_20140927_1006'),
    ]

    operations = [
        migrations.CreateModel(
            name='ItemVariation',
            fields=[
                ('id', models.AutoField(serialize=False, primary_key=True, verbose_name='ID', auto_created=True)),
                ('active', models.BooleanField(default=True)),
                ('default_price', models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True, verbose_name='Default price')),
                ('item', models.ForeignKey(related_name='variations', to='tixlbase.Item')),
                ('values', models.ManyToManyField(related_name='variations', to='tixlbase.PropertyValue')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.RemoveField(
            model_name='itemflavor',
            name='item',
        ),
        migrations.RemoveField(
            model_name='itemflavor',
            name='values',
        ),
        migrations.DeleteModel(
            name='ItemFlavor',
        ),
        migrations.AlterField(
            model_name='item',
            name='category',
            field=models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT, related_name='items', to='tixlbase.ItemCategory'),
        ),
        migrations.AlterField(
            model_name='item',
            name='event',
            field=models.ForeignKey(to='tixlbase.Event', on_delete=django.db.models.deletion.PROTECT, related_name='items'),
        ),
    ]
