# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0004_auto_20151024_0848'),
    ]

    operations = [
        migrations.AddField(
            model_name='item',
            name='available_from',
            field=models.DateTimeField(null=True, help_text='This product will not be sold before the given date.', blank=True, verbose_name='Available from'),
        ),
        migrations.AddField(
            model_name='item',
            name='available_until',
            field=models.DateTimeField(null=True, help_text='This product will not be sold after the given date.', blank=True, verbose_name='Available to'),
        ),
    ]
