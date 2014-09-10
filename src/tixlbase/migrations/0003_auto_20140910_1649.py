# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tixlbase', '0002_auto_20140910_1628'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='username',
            field=models.CharField(blank=True, max_length=120, null=True, help_text='Letters, digits and @/./+/-/_ only.'),
        ),
    ]
