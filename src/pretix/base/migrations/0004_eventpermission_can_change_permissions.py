# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0003_auto_20150602_2232'),
    ]

    operations = [
        migrations.AddField(
            model_name='eventpermission',
            name='can_change_permissions',
            field=models.BooleanField(default=True, verbose_name='Can change permissions'),
        ),
    ]
