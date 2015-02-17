# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.utils.timezone import utc
import versions.models
import datetime
import pretix.base.models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0003_auto_20150211_2042'),
    ]

    operations = [
        migrations.AddField(
            model_name='cartposition',
            name='identity',
            field=models.CharField(default='LEGACY', max_length=36),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='cartposition',
            name='version_birth_date',
            field=models.DateTimeField(default=datetime.datetime(2015, 2, 11, 23, 30, 3, 234665, tzinfo=utc)),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='cartposition',
            name='version_end_date',
            field=models.DateTimeField(blank=True, null=True, default=None),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='cartposition',
            name='version_start_date',
            field=models.DateTimeField(default=datetime.datetime(2015, 2, 11, 23, 30, 3, 234665, tzinfo=utc)),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='orderposition',
            name='identity',
            field=models.CharField(default='LEGACY', max_length=36),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='orderposition',
            name='version_birth_date',
            field=models.DateTimeField(default=datetime.datetime(2015, 2, 11, 23, 30, 15, 115790, tzinfo=utc)),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='orderposition',
            name='version_end_date',
            field=models.DateTimeField(blank=True, null=True, default=None),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='orderposition',
            name='version_start_date',
            field=models.DateTimeField(default=datetime.datetime(2015, 2, 11, 23, 30, 21, 726769, tzinfo=utc)),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='cartposition',
            name='id',
            field=models.CharField(primary_key=True, serialize=False, max_length=36),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='orderposition',
            name='id',
            field=models.CharField(primary_key=True, serialize=False, max_length=36),
            preserve_default=True,
        ),
    ]
