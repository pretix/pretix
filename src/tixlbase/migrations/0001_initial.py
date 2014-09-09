# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.utils.timezone
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True, serialize=False)),
                ('password', models.CharField(verbose_name='password', max_length=128)),
                ('last_login', models.DateTimeField(verbose_name='last login', default=django.utils.timezone.now)),
                ('is_superuser', models.BooleanField(verbose_name='superuser status', default=False, help_text='Designates that this user has all permissions without explicitly assigning them.')),
                ('identifier', models.CharField(unique=True, max_length=255)),
                ('username', models.CharField(max_length=120)),
                ('email', models.EmailField(blank=True, null=True, db_index=True, max_length=75)),
                ('is_active', models.BooleanField(default=True)),
                ('is_staff', models.BooleanField(default=False)),
                ('date_joined', models.DateTimeField(auto_now_add=True)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True, serialize=False)),
                ('name', models.CharField(max_length=200)),
                ('slug', models.CharField(db_index=True, max_length=50)),
                ('locale', models.CharField(max_length=10)),
                ('currency', models.CharField(max_length=10)),
                ('date_from', models.DateTimeField()),
                ('date_to', models.DateTimeField(blank=True, null=True)),
                ('show_date_to', models.BooleanField(default=True)),
                ('show_times', models.BooleanField(default=True)),
                ('presale_end', models.DateTimeField(blank=True, null=True)),
                ('presale_start', models.DateTimeField(blank=True, null=True)),
                ('payment_term_days', models.IntegerField(default=14)),
                ('payment_term_last', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'ordering': ('date_from', 'name'),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Organizer',
            fields=[
                ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True, serialize=False)),
                ('name', models.CharField(max_length=200)),
                ('slug', models.CharField(unique=True, db_index=True, max_length=50)),
                ('owner', models.ForeignKey(blank=True, null=True, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('name',),
            },
            bases=(models.Model,),
        ),
        migrations.AddField(
            model_name='event',
            name='organizer',
            field=models.ForeignKey(to='tixlbase.Organizer', related_name='events'),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='event',
            unique_together=set([('organizer', 'slug')]),
        ),
        migrations.AddField(
            model_name='user',
            name='event',
            field=models.ForeignKey(to='tixlbase.Event', blank=True, null=True, related_name='users'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='user',
            name='groups',
            field=models.ManyToManyField(verbose_name='groups', related_name='user_set', related_query_name='user', blank=True, to='auth.Group', help_text='The groups this user belongs to. A user will get all permissions granted to each of his/her group.'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='user',
            name='user_permissions',
            field=models.ManyToManyField(verbose_name='user permissions', related_name='user_set', related_query_name='user', blank=True, to='auth.Permission', help_text='Specific permissions for this user.'),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='user',
            unique_together=set([('event', 'username')]),
        ),
    ]
