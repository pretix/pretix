# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import versions.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixmultidomain', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='knowndomain',
            options={'verbose_name': 'Known domain', 'verbose_name_plural': 'Known domains'},
        ),
        migrations.AlterField(
            model_name='knowndomain',
            name='organizer',
            field=versions.models.VersionedForeignKey(to='pretixbase.Organizer', null=True, related_name='domains', blank=True),
        ),
    ]
