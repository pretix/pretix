# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tixlbase', '0007_auto_20140914_1301'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='timezone',
            field=models.CharField(max_length=100, default='UTC', verbose_name='Default timezone'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='user',
            name='locale',
            field=models.CharField(max_length=50, verbose_name='Language', default='en', choices=[('de', 'German'), ('en', 'English')]),
        ),
        migrations.AlterField(
            model_name='user',
            name='timezone',
            field=models.CharField(max_length=100, default='UTC', verbose_name='Timezone'),
        ),
    ]
