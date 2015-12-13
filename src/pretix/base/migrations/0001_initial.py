# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib.auth.hashers import make_password
from django.db import migrations, models


def initial_user(apps, schema_editor):
    User = apps.get_model("pretixbase", "User")
    user = User(email='admin@localhost')
    user.is_staff = True
    user.is_superuser = True
    user.password = make_password('admin')
    user.save()


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0006_require_contenttypes_0002'),
    ]

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True, serialize=False)),
                ('password', models.CharField(verbose_name='password', max_length=128)),
                ('last_login', models.DateTimeField(verbose_name='last login', blank=True, null=True)),
                ('is_superuser', models.BooleanField(verbose_name='superuser status', default=False, help_text='Designates that this user has all permissions without explicitly assigning them.')),
                ('email', models.EmailField(max_length=254, blank=True, unique=True, verbose_name='E-mail', null=True, db_index=True)),
                ('givenname', models.CharField(verbose_name='Given name', max_length=255, blank=True, null=True)),
                ('familyname', models.CharField(verbose_name='Family name', max_length=255, blank=True, null=True)),
                ('is_active', models.BooleanField(verbose_name='Is active', default=True)),
                ('is_staff', models.BooleanField(verbose_name='Is site admin', default=False)),
                ('date_joined', models.DateTimeField(verbose_name='Date joined', auto_now_add=True)),
                ('locale', models.CharField(verbose_name='Language', default='en', choices=[('en', 'English'), ('de', 'German'), ('de-informal', 'German (informal)')], max_length=50)),
                ('timezone', models.CharField(verbose_name='Timezone', default='UTC', max_length=100)),
                ('groups', models.ManyToManyField(to='auth.Group', blank=True, related_query_name='user', verbose_name='groups', help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.', related_name='user_set')),
                ('user_permissions', models.ManyToManyField(to='auth.Permission', blank=True, related_query_name='user', verbose_name='user permissions', help_text='Specific permissions for this user.', related_name='user_set')),
            ],
            options={
                'verbose_name': 'User',
                'verbose_name_plural': 'Users',
            },
        ),
        migrations.RunPython(initial_user),
    ]
