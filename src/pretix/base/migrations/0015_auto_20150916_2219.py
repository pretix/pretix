# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models

import pretix.base.models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0014_auto_20150916_1319'),
    ]

    operations = [
        migrations.AddField(
            model_name='cartposition',
            name='session',
            field=models.CharField(max_length=255, verbose_name='Session', null=True, blank=True),
        ),
        migrations.AddField(
            model_name='order',
            name='secret',
            field=models.CharField(max_length=32, default=pretix.base.models.generate_secret),
        ),
        migrations.AlterField(
            model_name='user',
            name='email',
            field=models.EmailField(max_length=254, verbose_name='E-mail', blank=True, db_index=True, unique=True, null=True),
        ),
        migrations.AlterUniqueTogether(
            name='user',
            unique_together=set([]),
        ),
        migrations.RemoveField(
            model_name='user',
            name='event',
        ),
        migrations.RemoveField(
            model_name='user',
            name='identifier',
        ),
        migrations.RemoveField(
            model_name='user',
            name='username',
        ),
    ]
