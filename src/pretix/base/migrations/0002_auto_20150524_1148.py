# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='organizer',
            name='slug',
            field=models.SlugField(verbose_name='Slug'),
        ),
    ]
