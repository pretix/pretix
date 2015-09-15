# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import versions.models
from django.db import migrations, models

import pretix.base.models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0008_auto_20150804_1357'),
    ]

    operations = [
        migrations.CreateModel(
            name='CachedFile',
            fields=[
                ('id', models.UUIDField(primary_key=True, serialize=False)),
                ('expires', models.DateTimeField(null=True, blank=True)),
                ('date', models.DateTimeField(null=True, blank=True)),
                ('filename', models.CharField(max_length=255)),
                ('file', models.FileField(null=True, upload_to=pretix.base.models.cachedfile_name, blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='CachedTicket',
            fields=[
                ('id', models.AutoField(primary_key=True, auto_created=True, verbose_name='ID', serialize=False)),
                ('provider', models.CharField(max_length=255)),
                ('cachedfile', models.ForeignKey(to='pretixbase.CachedFile')),
                ('order', models.ForeignKey(to='pretixbase.Order')),
            ],
        ),
        migrations.AlterModelOptions(
            name='itemcategory',
            options={'verbose_name_plural': 'Product categories', 'ordering': ('position', 'version_birth_date'), 'verbose_name': 'Product category'},
        ),
        migrations.AlterModelOptions(
            name='propertyvalue',
            options={'verbose_name_plural': 'Property values', 'ordering': ('position', 'version_birth_date'), 'verbose_name': 'Property value'},
        ),
        migrations.AlterField(
            model_name='orderposition',
            name='item',
            field=versions.models.VersionedForeignKey(to='pretixbase.Item', verbose_name='Item', related_name='positions'),
        ),
        migrations.AlterField(
            model_name='user',
            name='locale',
            field=models.CharField(choices=[('en', 'English'), ('de', 'German'), ('de-informal', 'German (informal)')], max_length=50, default='en', verbose_name='Language'),
        ),
        migrations.AddField(
            model_name='order',
            name='tickets',
            field=models.ManyToManyField(to='pretixbase.CachedFile', through='pretixbase.CachedTicket'),
        ),
    ]
