# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import versions.models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0018_auto_20150314_1232'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='event',
            field=versions.models.VersionedForeignKey(to='pretixbase.Event', related_name='orders', verbose_name='Event'),
        ),
        migrations.AlterField(
            model_name='order',
            name='user',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, blank=True, related_name='orders', null=True, verbose_name='User'),
        ),
    ]
