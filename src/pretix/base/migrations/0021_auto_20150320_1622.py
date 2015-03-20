# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0020_auto_20150319_1044'),
    ]

    operations = [
        migrations.AddField(
            model_name='eventpermission',
            name='can_change_orders',
            field=models.BooleanField(default=True, verbose_name='Can change orders'),
        ),
        migrations.AddField(
            model_name='eventpermission',
            name='can_view_orders',
            field=models.BooleanField(default=True, verbose_name='Can view orders'),
        ),
        migrations.AlterField(
            model_name='event',
            name='slug',
            field=models.SlugField(verbose_name='Slug', validators=[django.core.validators.RegexValidator(message='The slug may only contain letters, numbers, dots and dashes.', regex='^[a-zA-Z0-9.-]+$')], help_text='Should be short, only contain lowercase letters and numbers, and must be unique among your events. This is being used in addresses and bank transfer references.'),
        ),
    ]
