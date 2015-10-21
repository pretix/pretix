# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='quota',
            name='size',
            field=models.PositiveIntegerField(help_text='Leave empty for an unlimited number of tickets.', verbose_name='Total capacity', blank=True, null=True),
        ),
    ]
