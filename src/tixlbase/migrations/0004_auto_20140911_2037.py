# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tixlbase', '0003_auto_20140910_1649'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrganizerPermission',
            fields=[
                ('id', models.AutoField(auto_created=True, verbose_name='ID', serialize=False, primary_key=True)),
                ('can_create_events', models.BooleanField(default=True)),
                ('organizer', models.ForeignKey(to='tixlbase.Organizer', related_name='perms')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, related_name='organizer_perms')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='organizerpermission',
            unique_together=set([('organizer', 'user')]),
        ),
        migrations.RemoveField(
            model_name='organizer',
            name='owner',
        ),
        migrations.AlterField(
            model_name='event',
            name='organizer',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='events', to='tixlbase.Organizer'),
        ),
        migrations.AlterField(
            model_name='user',
            name='email',
            field=models.EmailField(null=True, blank=True, db_index=True, verbose_name='E-mail', max_length=75),
        ),
        migrations.AlterField(
            model_name='user',
            name='event',
            field=models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT, related_name='users', to='tixlbase.Event'),
        ),
        migrations.AlterField(
            model_name='user',
            name='familyname',
            field=models.CharField(null=True, blank=True, verbose_name='Family name', max_length=255),
        ),
        migrations.AlterField(
            model_name='user',
            name='givenname',
            field=models.CharField(null=True, blank=True, verbose_name='Given name', max_length=255),
        ),
    ]
