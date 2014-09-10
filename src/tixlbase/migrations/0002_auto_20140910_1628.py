# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tixlbase', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='familyname',
            field=models.CharField(blank=True, max_length=255, null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='user',
            name='givenname',
            field=models.CharField(blank=True, max_length=255, null=True),
            preserve_default=True,
        ),
    ]
