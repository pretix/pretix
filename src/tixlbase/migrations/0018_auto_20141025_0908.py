# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tixlbase', '0017_auto_20141017_2148'),
    ]

    operations = [
        migrations.AddField(
            model_name='quota',
            name='event',
            field=models.ForeignKey(to='tixlbase.Event', default=1, verbose_name='Event', related_name='quotas'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='cartposition',
            name='datetime',
            field=models.DateTimeField(verbose_name='Date'),
        ),
    ]
