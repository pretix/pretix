# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0002_auto_20150524_1148'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='item',
            options={'verbose_name_plural': 'Products', 'ordering': ('category__position', 'category', 'position'), 'verbose_name': 'Product'},
        ),
        migrations.AddField(
            model_name='item',
            name='position',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='organizer',
            name='slug',
            field=models.SlugField(help_text='Should be short, only contain lowercase letters and numbers, and must be unique among your events. This is being used in addresses and bank transfer references.', validators=[django.core.validators.RegexValidator(message='The slug may only contain letters, numbers, dots and dashes.', regex='^[a-zA-Z0-9.-]+$')], verbose_name='Slug'),
        ),
    ]
