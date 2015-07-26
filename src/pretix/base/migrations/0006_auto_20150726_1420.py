# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models

import pretix.base.models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0005_item_picture'),
    ]

    operations = [
        migrations.AlterField(
            model_name='item',
            name='picture',
            field=models.ImageField(upload_to=pretix.base.models.itempicture_upload_to, null=True, verbose_name='Product picture', blank=True),
        ),
    ]
