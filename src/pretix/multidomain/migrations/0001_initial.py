# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import versions.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='KnownDomain',
            fields=[
                ('domainname', models.CharField(serialize=False, max_length=255, primary_key=True)),
                ('organizer', versions.models.VersionedForeignKey(blank=True, to='pretixbase.Organizer', null=True)),
            ],
        ),
    ]
