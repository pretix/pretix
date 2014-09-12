# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tixlbase', '0005_auto_20140911_2052'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='event',
            options={'verbose_name_plural': 'Events', 'verbose_name': 'Event', 'ordering': ('date_from', 'name')},
        ),
        migrations.AlterModelOptions(
            name='eventpermission',
            options={'verbose_name_plural': 'Event permissions', 'verbose_name': 'Event permission'},
        ),
        migrations.AlterModelOptions(
            name='organizer',
            options={'verbose_name_plural': 'Organizers', 'verbose_name': 'Organizer', 'ordering': ('name',)},
        ),
        migrations.AlterModelOptions(
            name='organizerpermission',
            options={'verbose_name_plural': 'Organizer permissions', 'verbose_name': 'Organizer permission'},
        ),
        migrations.AlterModelOptions(
            name='user',
            options={'verbose_name_plural': 'Users', 'verbose_name': 'User'},
        ),
        migrations.RenameField(
            model_name='eventpermission',
            old_name='organizer',
            new_name='event',
        ),
        migrations.AlterField(
            model_name='event',
            name='currency',
            field=models.CharField(max_length=10, verbose_name='Default currency'),
        ),
        migrations.AlterField(
            model_name='event',
            name='date_from',
            field=models.DateTimeField(verbose_name='Event start time'),
        ),
        migrations.AlterField(
            model_name='event',
            name='date_to',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Event end time'),
        ),
        migrations.AlterField(
            model_name='event',
            name='locale',
            field=models.CharField(max_length=10, verbose_name='Default locale', choices=[('de', 'German'), ('en', 'English')]),
        ),
        migrations.AlterField(
            model_name='event',
            name='name',
            field=models.CharField(max_length=200, verbose_name='Name'),
        ),
        migrations.AlterField(
            model_name='event',
            name='payment_term_days',
            field=models.IntegerField(verbose_name='Payment term in days', default=14),
        ),
        migrations.AlterField(
            model_name='event',
            name='payment_term_last',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Last date of payments'),
        ),
        migrations.AlterField(
            model_name='event',
            name='presale_end',
            field=models.DateTimeField(blank=True, null=True, verbose_name='End of presale'),
        ),
        migrations.AlterField(
            model_name='event',
            name='presale_start',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Start of presale'),
        ),
        migrations.AlterField(
            model_name='event',
            name='show_date_to',
            field=models.BooleanField(verbose_name='Show event end date', default=True),
        ),
        migrations.AlterField(
            model_name='event',
            name='show_times',
            field=models.BooleanField(verbose_name='Show dates with time', default=True),
        ),
        migrations.AlterField(
            model_name='event',
            name='slug',
            field=models.CharField(db_index=True, max_length=50, verbose_name='Slug'),
        ),
        migrations.AlterField(
            model_name='eventpermission',
            name='can_change_settings',
            field=models.BooleanField(verbose_name='Can change event settings', default=True),
        ),
        migrations.AlterField(
            model_name='organizer',
            name='name',
            field=models.CharField(max_length=200, verbose_name='Name'),
        ),
        migrations.AlterField(
            model_name='organizer',
            name='slug',
            field=models.CharField(db_index=True, max_length=50, verbose_name='Slug', unique=True),
        ),
        migrations.AlterField(
            model_name='organizerpermission',
            name='can_create_events',
            field=models.BooleanField(verbose_name='Can create events', default=True),
        ),
        migrations.AlterField(
            model_name='user',
            name='date_joined',
            field=models.DateTimeField(verbose_name='Date joined', auto_now_add=True),
        ),
        migrations.AlterField(
            model_name='user',
            name='is_active',
            field=models.BooleanField(verbose_name='Is active', default=True),
        ),
        migrations.AlterField(
            model_name='user',
            name='is_staff',
            field=models.BooleanField(verbose_name='Is site admin', default=False),
        ),
        migrations.AlterUniqueTogether(
            name='eventpermission',
            unique_together=set([('event', 'user')]),
        ),
    ]
