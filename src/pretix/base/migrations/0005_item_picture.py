# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0004_eventpermission_can_change_permissions'),
    ]

    operations = [
        migrations.AddField(
            model_name='item',
            name='picture',
            field=models.ImageField(upload_to='', null=True, verbose_name='Product picture', blank=True),
        ),
    ]
