# -*- coding: utf-8 -*-
# Generated by Django 1.9.2 on 2016-03-12 10:40
from __future__ import unicode_literals

import datetime
from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models

import pretix.base.models.invoices


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0011_auto_20160311_2052'),
    ]

    operations = [
        migrations.CreateModel(
            name='Invoice',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('invoice_no', models.PositiveIntegerField(db_index=True)),
                ('is_cancelled', models.BooleanField(default=False)),
                ('invoice_from', models.TextField()),
                ('invoice_to', models.TextField()),
                ('date', models.DateField(default=datetime.date.today)),
                ('file', models.FileField(blank=True, null=True, upload_to=pretix.base.models.invoices.invoice_filename)),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='invoices', to='pretixbase.Event')),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='invoices', to='pretixbase.Order')),
            ],
        ),
        migrations.CreateModel(
            name='InvoiceLine',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.TextField()),
                ('gross_value', models.DecimalField(decimal_places=2, max_digits=10)),
                ('tax_value', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10)),
                ('tax_rate', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=7)),
                ('invoice', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lines', to='pretixbase.Invoice')),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='invoice',
            unique_together=set([('event', 'invoice_no')]),
        ),
    ]
