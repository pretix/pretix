# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='KnownDomain',
            fields=[
                ('domainname', models.CharField(primary_key=True, max_length=255, serialize=False)),
                ('organizer', models.ForeignKey(to='pretixbase.Organizer', null=True, blank=True, related_name='domains')),
            ],
            options={
                'verbose_name_plural': 'Known domains',
                'verbose_name': 'Known domain',
            },
        ),
    ]
