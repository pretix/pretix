# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import versions.models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0008_quota_locked'),
    ]

    operations = [
        migrations.CreateModel(
            name='EventSetting',
            fields=[
                ('id', models.CharField(primary_key=True, serialize=False, max_length=36)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('key', models.CharField(max_length=255)),
                ('value', models.TextField()),
                ('event', versions.models.VersionedForeignKey(related_name='setting_objects', to='pretixbase.Event')),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='OrganizerSetting',
            fields=[
                ('id', models.CharField(primary_key=True, serialize=False, max_length=36)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('key', models.CharField(max_length=255)),
                ('value', models.TextField()),
                ('organizer', versions.models.VersionedForeignKey(related_name='setting_objects', to='pretixbase.Organizer')),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
    ]
