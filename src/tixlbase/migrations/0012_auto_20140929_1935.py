# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.db.models.deletion

def setposition(apps, schema_editor):
    ItemCategory = apps.get_model("tixlbase", "ItemCategory")
    for cat in ItemCategory.objects.all():
        cat.position = 0
        cat.save()

class Migration(migrations.Migration):

    dependencies = [
        ('tixlbase', '0011_auto_20140927_1013'),
    ]

    operations = [
        migrations.RunPython(setposition),
        migrations.AlterField(
            model_name='item',
            name='active',
            field=models.BooleanField(default=True, verbose_name='Active'),
        ),
        migrations.AlterField(
            model_name='item',
            name='category',
            field=models.ForeignKey(blank=True, null=True, verbose_name='Category', related_name='items', to='tixlbase.ItemCategory', on_delete=django.db.models.deletion.PROTECT),
        ),
        migrations.AlterField(
            model_name='item',
            name='event',
            field=models.ForeignKey(to='tixlbase.Event', related_name='items', verbose_name='Event', on_delete=django.db.models.deletion.PROTECT),
        ),
        migrations.AlterField(
            model_name='item',
            name='properties',
            field=models.ManyToManyField(to='tixlbase.Property', help_text="The selected properties will be available for the user to select. After saving this field, move to the 'Variations' tab to configure the details.", blank=True, verbose_name='Properties', related_name='items'),
        ),
        migrations.AlterField(
            model_name='item',
            name='tax_rate',
            field=models.DecimalField(max_digits=7, verbose_name='Taxes included in percent', blank=True, null=True, decimal_places=2),
        ),
        migrations.AlterField(
            model_name='itemcategory',
            name='event',
            field=models.ForeignKey(related_name='categories', to='tixlbase.Event'),
        ),
        migrations.AlterField(
            model_name='itemcategory',
            name='position',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='itemvariation',
            name='active',
            field=models.BooleanField(default=True, verbose_name='Active'),
        ),
        migrations.AlterField(
            model_name='property',
            name='event',
            field=models.ForeignKey(related_name='properties', to='tixlbase.Event'),
        ),
    ]
