# -*- coding: utf-8 -*-
# Generated by Django 1.11.2 on 2017-07-04 15:57
from __future__ import unicode_literals

import django.db.models.deletion
import i18nfield.fields
from django.db import migrations, models

import pretix.base.models.base
import pretix.base.models.event


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0064_auto_20170703_0912'),
    ]

    operations = [
        migrations.CreateModel(
            name='SubEvent',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('active', models.BooleanField(default=False, help_text='Only with this checkbox enabled, this sub-event is visible in the frontend to users.', verbose_name='Active')),
                ('name', i18nfield.fields.I18nCharField(max_length=200, verbose_name='Name')),
                ('date_from', models.DateTimeField(verbose_name='Event start time')),
                ('date_to', models.DateTimeField(blank=True, null=True, verbose_name='Event end time')),
                ('date_admission', models.DateTimeField(blank=True, null=True, verbose_name='Admission time')),
                ('presale_end', models.DateTimeField(blank=True, help_text='No products will be sold after this date.', null=True, verbose_name='End of presale')),
                ('presale_start', models.DateTimeField(blank=True, help_text='No products will be sold before this date.', null=True, verbose_name='Start of presale')),
                ('location', i18nfield.fields.I18nTextField(blank=True, max_length=200, null=True, verbose_name='Location')),
            ],
            options={
                'verbose_name_plural': 'Sub-Events',
                'verbose_name': 'Sub-Event',
                'ordering': ('date_from', 'name'),
            },
            bases=(pretix.base.models.event.EventMixin, models.Model, pretix.base.models.base.LoggingMixin),
        ),
        migrations.CreateModel(
            name='SubEventItem',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('price', models.DecimalField(blank=True, decimal_places=2, max_digits=7, null=True)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='pretixbase.Item')),
                ('subevent', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='pretixbase.SubEvent')),
            ],
        ),
        migrations.CreateModel(
            name='SubEventItemVariation',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('price', models.DecimalField(blank=True, decimal_places=2, max_digits=7, null=True)),
                ('subevent', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='pretixbase.SubEvent')),
                ('variation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='pretixbase.ItemVariation')),
            ],
        ),
        migrations.AddField(
            model_name='event',
            name='has_subevents',
            field=models.BooleanField(default=False, verbose_name='Use sub-event functionality'),
        ),
        migrations.AddField(
            model_name='subevent',
            name='event',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='subevents', to='pretixbase.Event'),
        ),
        migrations.AddField(
            model_name='subevent',
            name='items',
            field=models.ManyToManyField(through='pretixbase.SubEventItem', to='pretixbase.Item'),
        ),
        migrations.AddField(
            model_name='subevent',
            name='variations',
            field=models.ManyToManyField(through='pretixbase.SubEventItemVariation', to='pretixbase.ItemVariation'),
        ),
        migrations.AddField(
            model_name='cartposition',
            name='subevent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='pretixbase.SubEvent', verbose_name='Sub-event'),
        ),
        migrations.AddField(
            model_name='orderposition',
            name='subevent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='pretixbase.SubEvent', verbose_name='Sub-event'),
        ),
        migrations.AddField(
            model_name='quota',
            name='subevent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='quotas', to='pretixbase.SubEvent', verbose_name='Sub-event'),
        ),
        migrations.AddField(
            model_name='voucher',
            name='subevent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='pretixbase.SubEvent', verbose_name='Sub-event'),
        ),
        migrations.AddField(
            model_name='waitinglistentry',
            name='subevent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='pretixbase.SubEvent', verbose_name='Sub-event'),
        ),
    ]
