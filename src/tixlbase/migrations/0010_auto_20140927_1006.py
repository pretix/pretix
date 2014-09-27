# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tixlbase', '0009_auto_20140916_2120'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='itemflavor',
            name='prop',
        ),
        migrations.AddField(
            model_name='eventpermission',
            name='can_change_items',
            field=models.BooleanField(verbose_name='Can change item settings', default=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='itemflavor',
            name='values',
            field=models.ManyToManyField(to='tixlbase.PropertyValue', related_name='flavors'),
            preserve_default=True,
        ),
    ]
