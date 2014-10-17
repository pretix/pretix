# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import tixlbase.models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('tixlbase', '0016_event_plugins'),
    ]

    operations = [
        migrations.CreateModel(
            name='CartPosition',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False, verbose_name='ID', auto_created=True)),
                ('session', models.CharField(null=True, max_length=255, blank=True, verbose_name='Session key')),
                ('total', models.DecimalField(max_digits=10, verbose_name='Price', decimal_places=2)),
                ('datetime', models.DateTimeField(verbose_name='Datetime')),
                ('expires', models.DateTimeField(verbose_name='Expiration date')),
                ('event', models.ForeignKey(to='tixlbase.Event', verbose_name='Event')),
                ('item', models.ForeignKey(to='tixlbase.Item', verbose_name='Item')),
                ('user', models.ForeignKey(null=True, blank=True, to=settings.AUTH_USER_MODEL, verbose_name='User')),
                ('variation', models.ForeignKey(null=True, blank=True, to='tixlbase.ItemVariation', verbose_name='Variation')),
            ],
            options={
                'verbose_name_plural': 'Cart positions',
                'verbose_name': 'Cart position',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Order',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False, verbose_name='ID', auto_created=True)),
                ('status', models.CharField(max_length=3, choices=[('p', 'pending'), ('n', 'paid'), ('e', 'expired'), ('c', 'cancelled')], verbose_name='Status')),
                ('datetime', models.DateTimeField(auto_now_add=True, verbose_name='Date')),
                ('expires', models.DateTimeField(verbose_name='Expiration date')),
                ('payment_date', models.DateTimeField(verbose_name='Payment date')),
                ('payment_info', models.TextField(verbose_name='Payment information')),
                ('total', models.DecimalField(max_digits=10, verbose_name='Total amount', decimal_places=2)),
                ('event', models.ForeignKey(to='tixlbase.Event', verbose_name='Event')),
                ('user', models.ForeignKey(null=True, blank=True, to=settings.AUTH_USER_MODEL, verbose_name='User')),
            ],
            options={
                'verbose_name_plural': 'Orders',
                'verbose_name': 'Order',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='OrderPosition',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False, verbose_name='ID', auto_created=True)),
                ('price', models.DecimalField(max_digits=10, verbose_name='Price', decimal_places=2)),
            ],
            options={
                'verbose_name_plural': 'Order positions',
                'verbose_name': 'Order position',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='QuestionAnswer',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False, verbose_name='ID', auto_created=True)),
                ('answer', models.TextField()),
                ('cartposition', models.ForeignKey(null=True, blank=True, to='tixlbase.CartPosition')),
                ('orderposition', models.ForeignKey(null=True, blank=True, to='tixlbase.OrderPosition')),
                ('question', models.ForeignKey(to='tixlbase.Question')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Quota',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False, verbose_name='ID', auto_created=True)),
                ('name', models.CharField(max_length=200, verbose_name='Name')),
                ('size', models.PositiveIntegerField(verbose_name='Total capacity')),
                ('items', models.ManyToManyField(to='tixlbase.Item', blank=True, verbose_name='Item')),
                ('lock_cache', models.ManyToManyField(to='tixlbase.CartPosition', blank=True)),
                ('order_cache', models.ManyToManyField(to='tixlbase.OrderPosition', blank=True)),
                ('variations', tixlbase.models.VariationsField(to='tixlbase.ItemVariation', blank=True, verbose_name='Variations')),
            ],
            options={
                'verbose_name_plural': 'Quotas',
                'verbose_name': 'Quota',
            },
            bases=(models.Model,),
        ),
        migrations.AddField(
            model_name='orderposition',
            name='answers',
            field=models.ManyToManyField(to='tixlbase.Question', through='tixlbase.QuestionAnswer', verbose_name='Answers'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='orderposition',
            name='item',
            field=models.ForeignKey(to='tixlbase.Item', verbose_name='Item'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='orderposition',
            name='order',
            field=models.ForeignKey(to='tixlbase.Order', verbose_name='Order'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='orderposition',
            name='variation',
            field=models.ForeignKey(null=True, blank=True, to='tixlbase.ItemVariation', verbose_name='Variation'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='event',
            name='payment_term_days',
            field=models.PositiveIntegerField(verbose_name='Payment term in days', default=14, help_text='The number of days after placing an order the user has to pay to preserve his reservation.'),
        ),
    ]
