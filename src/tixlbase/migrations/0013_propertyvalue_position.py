# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tixlbase', '0012_auto_20140929_1935'),
    ]

    operations = [
        migrations.AddField(
            model_name='propertyvalue',
            name='position',
            field=models.IntegerField(default=0),
            preserve_default=True,
        ),
    ]
