# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('tixlbase', '0004_auto_20140911_2037'),
    ]

    operations = [
        migrations.CreateModel(
            name='EventPermission',
            fields=[
                ('id', models.AutoField(auto_created=True, serialize=False, primary_key=True, verbose_name='ID')),
                ('can_change_settings', models.BooleanField(default=True)),
                ('organizer', models.ForeignKey(to='tixlbase.Event')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, related_name='event_perms')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='eventpermission',
            unique_together=set([('organizer', 'user')]),
        ),
        migrations.AddField(
            model_name='event',
            name='permitted',
            field=models.ManyToManyField(to=settings.AUTH_USER_MODEL, related_name='events', through='tixlbase.EventPermission'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='organizer',
            name='permitted',
            field=models.ManyToManyField(to=settings.AUTH_USER_MODEL, related_name='organizers', through='tixlbase.OrganizerPermission'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='organizerpermission',
            name='organizer',
            field=models.ForeignKey(to='tixlbase.Organizer'),
        ),
    ]
