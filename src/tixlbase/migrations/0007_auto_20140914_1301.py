# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tixlbase', '0006_auto_20140912_1855'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='locale',
            field=models.CharField(choices=[('de', 'German'), ('en', 'English')], max_length=50, default='en'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='user',
            name='timezone',
            field=models.CharField(max_length=100, default='UTC'),
            preserve_default=True,
        ),
    ]
