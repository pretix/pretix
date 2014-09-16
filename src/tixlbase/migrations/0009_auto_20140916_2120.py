# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tixlbase', '0008_auto_20140914_1304'),
    ]

    operations = [
        migrations.CreateModel(
            name='Item',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False, auto_created=True, verbose_name='ID')),
                ('name', models.CharField(max_length=255, verbose_name='Item name')),
                ('active', models.BooleanField(default=True)),
                ('deleted', models.BooleanField(default=False)),
                ('short_description', models.TextField(help_text='This is shown below the item name in lists.', blank=True, null=True, verbose_name='Short description')),
                ('long_description', models.TextField(blank=True, null=True, verbose_name='Long description')),
                ('default_price', models.DecimalField(decimal_places=2, blank=True, max_digits=7, null=True, verbose_name='Default price')),
                ('tax_rate', models.DecimalField(decimal_places=2, blank=True, max_digits=7, null=True, verbose_name='Included taxes in percent')),
            ],
            options={
                'verbose_name_plural': 'Items',
                'verbose_name': 'Item',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='ItemCategory',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False, auto_created=True, verbose_name='ID')),
                ('name', models.CharField(max_length=255, verbose_name='Category name')),
                ('position', models.IntegerField(blank=True, null=True)),
                ('event', models.ForeignKey(to='tixlbase.Event')),
            ],
            options={
                'verbose_name_plural': 'Item categories',
                'ordering': ('position',),
                'verbose_name': 'Item category',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='ItemFlavor',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False, auto_created=True, verbose_name='ID')),
                ('active', models.BooleanField(default=True)),
                ('default_price', models.DecimalField(decimal_places=2, blank=True, max_digits=7, null=True, verbose_name='Default price')),
                ('item', models.ForeignKey(to='tixlbase.Item', related_name='flavors')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Property',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False, auto_created=True, verbose_name='ID')),
                ('name', models.CharField(max_length=250, verbose_name='Property name')),
                ('event', models.ForeignKey(to='tixlbase.Event')),
            ],
            options={
                'verbose_name_plural': 'Item properties',
                'verbose_name': 'Item property',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='PropertyValue',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False, auto_created=True, verbose_name='ID')),
                ('value', models.CharField(max_length=250, verbose_name='Value')),
                ('prop', models.ForeignKey(to='tixlbase.Property', related_name='values')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.AddField(
            model_name='itemflavor',
            name='prop',
            field=models.ManyToManyField(related_name='values', to='tixlbase.PropertyValue'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='item',
            name='category',
            field=models.ForeignKey(blank=True, to='tixlbase.ItemCategory', on_delete=django.db.models.deletion.PROTECT, null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='item',
            name='event',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='tixlbase.Event'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='item',
            name='properties',
            field=models.ManyToManyField(related_name='items', to='tixlbase.Property'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='event',
            name='payment_term_days',
            field=models.IntegerField(help_text='The number of days after placing an order the user has to pay to preserve his reservation.', default=14, verbose_name='Payment term in days'),
        ),
        migrations.AlterField(
            model_name='event',
            name='payment_term_last',
            field=models.DateTimeField(help_text='The last date any payments are accepted. This has precedence over the number of days configured above.', blank=True, null=True, verbose_name='Last date of payments'),
        ),
        migrations.AlterField(
            model_name='event',
            name='presale_end',
            field=models.DateTimeField(help_text='No items will be sold after this date.', blank=True, null=True, verbose_name='End of presale'),
        ),
        migrations.AlterField(
            model_name='event',
            name='presale_start',
            field=models.DateTimeField(help_text='No items will be sold before this date.', blank=True, null=True, verbose_name='Start of presale'),
        ),
        migrations.AlterField(
            model_name='event',
            name='show_date_to',
            field=models.BooleanField(help_text="If disabled, only event's start date will be displayed to the public.", default=True, verbose_name='Show event end date'),
        ),
        migrations.AlterField(
            model_name='event',
            name='show_times',
            field=models.BooleanField(help_text="If disabled, the event's start and end date will be displayed without the time of day.", default=True, verbose_name='Show dates with time'),
        ),
        migrations.AlterField(
            model_name='event',
            name='slug',
            field=models.CharField(db_index=True, help_text='Should be short, only contain lowercase letters and numbers, and must be unique among your events. This is being used in addresses and bank transfer references.', validators=[django.core.validators.RegexValidator(message='The slug may only contain letters, numbers, dots and dashes.', regex='^[a-zA-Z0-9.-]+$')], verbose_name='Slug', max_length=50),
        ),
    ]
