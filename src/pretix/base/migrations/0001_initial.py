# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import uuid

import django.core.validators
import django.db.models.deletion
import versions.models
from django.conf import settings
from django.db import migrations, models

import pretix.base.i18n
import pretix.base.models


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0006_require_contenttypes_0002'),
    ]

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                ('id', models.AutoField(serialize=False, verbose_name='ID', primary_key=True, auto_created=True)),
                ('password', models.CharField(verbose_name='password', max_length=128)),
                ('last_login', models.DateTimeField(verbose_name='last login', null=True, blank=True)),
                ('is_superuser', models.BooleanField(default=False, verbose_name='superuser status', help_text='Designates that this user has all permissions without explicitly assigning them.')),
                ('email', models.EmailField(unique=True, verbose_name='E-mail', blank=True, db_index=True, max_length=254, null=True)),
                ('givenname', models.CharField(verbose_name='Given name', null=True, max_length=255, blank=True)),
                ('familyname', models.CharField(verbose_name='Family name', null=True, max_length=255, blank=True)),
                ('is_active', models.BooleanField(default=True, verbose_name='Is active')),
                ('is_staff', models.BooleanField(default=False, verbose_name='Is site admin')),
                ('date_joined', models.DateTimeField(verbose_name='Date joined', auto_now_add=True)),
                ('locale', models.CharField(default='en', verbose_name='Language', choices=[('en', 'English'), ('de', 'German'), ('de-informal', 'German (informal)')], max_length=50)),
                ('timezone', models.CharField(default='UTC', verbose_name='Timezone', max_length=100)),
                ('groups', models.ManyToManyField(related_query_name='user', verbose_name='groups', help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.', blank=True, related_name='user_set', to='auth.Group')),
                ('user_permissions', models.ManyToManyField(related_query_name='user', verbose_name='user permissions', help_text='Specific permissions for this user.', blank=True, related_name='user_set', to='auth.Permission')),
            ],
            options={
                'verbose_name': 'User',
                'verbose_name_plural': 'Users',
            },
        ),
        migrations.CreateModel(
            name='CachedFile',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('expires', models.DateTimeField(null=True, blank=True)),
                ('date', models.DateTimeField(null=True, blank=True)),
                ('filename', models.CharField(max_length=255)),
                ('type', models.CharField(max_length=255)),
                ('file', models.FileField(upload_to=pretix.base.models.cachedfile_name, null=True, blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='CachedTicket',
            fields=[
                ('id', models.AutoField(serialize=False, verbose_name='ID', primary_key=True, auto_created=True)),
                ('provider', models.CharField(max_length=255)),
                ('cachedfile', models.ForeignKey(to='pretixbase.CachedFile')),
            ],
        ),
        migrations.CreateModel(
            name='CartPosition',
            fields=[
                ('id', models.CharField(serialize=False, max_length=36, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(default=None, null=True, blank=True)),
                ('version_birth_date', models.DateTimeField()),
                ('session', models.CharField(verbose_name='Session', null=True, max_length=255, blank=True)),
                ('price', models.DecimalField(decimal_places=2, verbose_name='Price', max_digits=10)),
                ('datetime', models.DateTimeField(verbose_name='Date', auto_now_add=True)),
                ('expires', models.DateTimeField(verbose_name='Expiration date')),
                ('attendee_name', models.CharField(verbose_name='Attendee name', null=True, help_text='Empty, if this product is not an admission ticket', max_length=255, blank=True)),
            ],
            options={
                'verbose_name': 'Cart position',
                'verbose_name_plural': 'Cart positions',
            },
            bases=(pretix.base.models.ObjectWithAnswers, models.Model),
        ),
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.CharField(serialize=False, max_length=36, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(default=None, null=True, blank=True)),
                ('version_birth_date', models.DateTimeField()),
                ('name', pretix.base.i18n.I18nCharField(verbose_name='Name', max_length=200)),
                ('slug', models.SlugField(verbose_name='Slug', help_text='Should be short, only contain lowercase letters and numbers, and must be unique among your events. This is being used in addresses and bank transfer references.', validators=[django.core.validators.RegexValidator(regex='^[a-zA-Z0-9.-]+$', message='The slug may only contain letters, numbers, dots and dashes.')])),
                ('currency', models.CharField(default='EUR', verbose_name='Default currency', max_length=10)),
                ('date_from', models.DateTimeField(verbose_name='Event start time')),
                ('date_to', models.DateTimeField(verbose_name='Event end time', null=True, blank=True)),
                ('presale_end', models.DateTimeField(verbose_name='End of presale', help_text='No products will be sold after this date.', null=True, blank=True)),
                ('presale_start', models.DateTimeField(verbose_name='Start of presale', help_text='No products will be sold before this date.', null=True, blank=True)),
                ('plugins', models.TextField(verbose_name='Plugins', null=True, blank=True)),
            ],
            options={
                'verbose_name': 'Event',
                'verbose_name_plural': 'Events',
                'ordering': ('date_from', 'name'),
            },
        ),
        migrations.CreateModel(
            name='EventLock',
            fields=[
                ('event', models.CharField(serialize=False, max_length=36, primary_key=True)),
                ('date', models.DateTimeField(auto_now=True)),
                ('token', models.UUIDField(default=uuid.uuid4)),
            ],
        ),
        migrations.CreateModel(
            name='EventPermission',
            fields=[
                ('id', models.CharField(serialize=False, max_length=36, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(default=None, null=True, blank=True)),
                ('version_birth_date', models.DateTimeField()),
                ('can_change_settings', models.BooleanField(default=True, verbose_name='Can change event settings')),
                ('can_change_items', models.BooleanField(default=True, verbose_name='Can change product settings')),
                ('can_view_orders', models.BooleanField(default=True, verbose_name='Can view orders')),
                ('can_change_permissions', models.BooleanField(default=True, verbose_name='Can change permissions')),
                ('can_change_orders', models.BooleanField(default=True, verbose_name='Can change orders')),
                ('event', versions.models.VersionedForeignKey(to='pretixbase.Event')),
                ('user', models.ForeignKey(related_name='event_perms', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Event permission',
                'verbose_name_plural': 'Event permissions',
            },
        ),
        migrations.CreateModel(
            name='EventSetting',
            fields=[
                ('id', models.CharField(serialize=False, max_length=36, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(default=None, null=True, blank=True)),
                ('version_birth_date', models.DateTimeField()),
                ('key', models.CharField(max_length=255)),
                ('value', models.TextField()),
                ('object', versions.models.VersionedForeignKey(related_name='setting_objects', to='pretixbase.Event')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Item',
            fields=[
                ('id', models.CharField(serialize=False, max_length=36, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(default=None, null=True, blank=True)),
                ('version_birth_date', models.DateTimeField()),
                ('name', pretix.base.i18n.I18nCharField(verbose_name='Item name', max_length=255)),
                ('active', models.BooleanField(default=True, verbose_name='Active')),
                ('description', pretix.base.i18n.I18nTextField(verbose_name='Description', help_text='This is shown below the product name in lists.', null=True, blank=True)),
                ('default_price', models.DecimalField(decimal_places=2, verbose_name='Default price', max_digits=7, null=True)),
                ('tax_rate', models.DecimalField(decimal_places=2, verbose_name='Taxes included in percent', max_digits=7, null=True, blank=True)),
                ('admission', models.BooleanField(default=False, verbose_name='Is an admission ticket', help_text='Whether or not buying this product allows a person to enter your event')),
                ('position', models.IntegerField(default=0)),
                ('picture', models.ImageField(upload_to=pretix.base.models.itempicture_upload_to, verbose_name='Product picture', null=True, blank=True)),
            ],
            options={
                'verbose_name': 'Product',
                'verbose_name_plural': 'Products',
                'ordering': ('category__position', 'category', 'position'),
            },
        ),
        migrations.CreateModel(
            name='ItemCategory',
            fields=[
                ('id', models.CharField(serialize=False, max_length=36, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(default=None, null=True, blank=True)),
                ('version_birth_date', models.DateTimeField()),
                ('name', pretix.base.i18n.I18nCharField(verbose_name='Category name', max_length=255)),
                ('position', models.IntegerField(default=0)),
                ('event', versions.models.VersionedForeignKey(related_name='categories', to='pretixbase.Event')),
            ],
            options={
                'verbose_name': 'Product category',
                'verbose_name_plural': 'Product categories',
                'ordering': ('position', 'version_birth_date'),
            },
        ),
        migrations.CreateModel(
            name='ItemVariation',
            fields=[
                ('id', models.CharField(serialize=False, max_length=36, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(default=None, null=True, blank=True)),
                ('version_birth_date', models.DateTimeField()),
                ('active', models.BooleanField(default=True, verbose_name='Active')),
                ('default_price', models.DecimalField(decimal_places=2, verbose_name='Default price', max_digits=7, null=True, blank=True)),
                ('item', versions.models.VersionedForeignKey(related_name='variations', to='pretixbase.Item')),
            ],
            options={
                'verbose_name': 'Product variation',
                'verbose_name_plural': 'Product variations',
            },
        ),
        migrations.CreateModel(
            name='Order',
            fields=[
                ('id', models.CharField(serialize=False, max_length=36, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(default=None, null=True, blank=True)),
                ('version_birth_date', models.DateTimeField()),
                ('code', models.CharField(verbose_name='Order code', max_length=16)),
                ('status', models.CharField(verbose_name='Status', choices=[('n', 'pending'), ('p', 'paid'), ('e', 'expired'), ('c', 'cancelled'), ('r', 'refunded')], max_length=3)),
                ('email', models.EmailField(verbose_name='E-mail', null=True, max_length=254, blank=True)),
                ('locale', models.CharField(verbose_name='Locale', null=True, max_length=32, blank=True)),
                ('secret', models.CharField(default=pretix.base.models.generate_secret, max_length=32)),
                ('datetime', models.DateTimeField(verbose_name='Date')),
                ('expires', models.DateTimeField(verbose_name='Expiration date')),
                ('payment_date', models.DateTimeField(verbose_name='Payment date', null=True, blank=True)),
                ('payment_provider', models.CharField(verbose_name='Payment provider', null=True, max_length=255, blank=True)),
                ('payment_fee', models.DecimalField(decimal_places=2, default=0, verbose_name='Payment method fee', max_digits=10)),
                ('payment_info', models.TextField(verbose_name='Payment information', null=True, blank=True)),
                ('payment_manual', models.BooleanField(default=False, verbose_name='Payment state was manually modified')),
                ('total', models.DecimalField(decimal_places=2, verbose_name='Total amount', max_digits=10)),
                ('event', versions.models.VersionedForeignKey(verbose_name='Event', related_name='orders', to='pretixbase.Event')),
            ],
            options={
                'verbose_name': 'Order',
                'verbose_name_plural': 'Orders',
                'ordering': ('-datetime',),
            },
        ),
        migrations.CreateModel(
            name='OrderPosition',
            fields=[
                ('id', models.CharField(serialize=False, max_length=36, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(default=None, null=True, blank=True)),
                ('version_birth_date', models.DateTimeField()),
                ('price', models.DecimalField(decimal_places=2, verbose_name='Price', max_digits=10)),
                ('attendee_name', models.CharField(verbose_name='Attendee name', null=True, help_text='Empty, if this product is not an admission ticket', max_length=255, blank=True)),
                ('item', versions.models.VersionedForeignKey(verbose_name='Item', related_name='positions', to='pretixbase.Item')),
                ('order', versions.models.VersionedForeignKey(verbose_name='Order', related_name='positions', to='pretixbase.Order')),
                ('variation', versions.models.VersionedForeignKey(verbose_name='Variation', blank=True, null=True, to='pretixbase.ItemVariation')),
            ],
            options={
                'verbose_name': 'Order position',
                'verbose_name_plural': 'Order positions',
            },
            bases=(pretix.base.models.ObjectWithAnswers, models.Model),
        ),
        migrations.CreateModel(
            name='Organizer',
            fields=[
                ('id', models.CharField(serialize=False, max_length=36, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(default=None, null=True, blank=True)),
                ('version_birth_date', models.DateTimeField()),
                ('name', models.CharField(verbose_name='Name', max_length=200)),
                ('slug', models.SlugField(verbose_name='Slug', help_text='Should be short, only contain lowercase letters and numbers, and must be unique among your events. This is being used in addresses and bank transfer references.', validators=[django.core.validators.RegexValidator(regex='^[a-zA-Z0-9.-]+$', message='The slug may only contain letters, numbers, dots and dashes.')])),
            ],
            options={
                'verbose_name': 'Organizer',
                'verbose_name_plural': 'Organizers',
                'ordering': ('name',),
            },
        ),
        migrations.CreateModel(
            name='OrganizerPermission',
            fields=[
                ('id', models.CharField(serialize=False, max_length=36, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(default=None, null=True, blank=True)),
                ('version_birth_date', models.DateTimeField()),
                ('can_create_events', models.BooleanField(default=True, verbose_name='Can create events')),
                ('organizer', versions.models.VersionedForeignKey(to='pretixbase.Organizer')),
                ('user', models.ForeignKey(related_name='organizer_perms', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Organizer permission',
                'verbose_name_plural': 'Organizer permissions',
            },
        ),
        migrations.CreateModel(
            name='OrganizerSetting',
            fields=[
                ('id', models.CharField(serialize=False, max_length=36, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(default=None, null=True, blank=True)),
                ('version_birth_date', models.DateTimeField()),
                ('key', models.CharField(max_length=255)),
                ('value', models.TextField()),
                ('object', versions.models.VersionedForeignKey(related_name='setting_objects', to='pretixbase.Organizer')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Property',
            fields=[
                ('id', models.CharField(serialize=False, max_length=36, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(default=None, null=True, blank=True)),
                ('version_birth_date', models.DateTimeField()),
                ('name', pretix.base.i18n.I18nCharField(verbose_name='Property name', max_length=250)),
                ('event', versions.models.VersionedForeignKey(related_name='properties', to='pretixbase.Event')),
                ('item', versions.models.VersionedForeignKey(blank=True, related_name='properties', null=True, to='pretixbase.Item')),
            ],
            options={
                'verbose_name': 'Product property',
                'verbose_name_plural': 'Product properties',
            },
        ),
        migrations.CreateModel(
            name='PropertyValue',
            fields=[
                ('id', models.CharField(serialize=False, max_length=36, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(default=None, null=True, blank=True)),
                ('version_birth_date', models.DateTimeField()),
                ('value', pretix.base.i18n.I18nCharField(verbose_name='Value', max_length=250)),
                ('position', models.IntegerField(default=0)),
                ('prop', versions.models.VersionedForeignKey(related_name='values', to='pretixbase.Property')),
            ],
            options={
                'verbose_name': 'Property value',
                'verbose_name_plural': 'Property values',
                'ordering': ('position', 'version_birth_date'),
            },
        ),
        migrations.CreateModel(
            name='Question',
            fields=[
                ('id', models.CharField(serialize=False, max_length=36, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(default=None, null=True, blank=True)),
                ('version_birth_date', models.DateTimeField()),
                ('question', pretix.base.i18n.I18nTextField(verbose_name='Question')),
                ('type', models.CharField(verbose_name='Question type', choices=[('N', 'Number'), ('S', 'Text (one line)'), ('T', 'Multiline text'), ('B', 'Yes/No')], max_length=5)),
                ('required', models.BooleanField(default=False, verbose_name='Required question')),
                ('event', versions.models.VersionedForeignKey(related_name='questions', to='pretixbase.Event')),
                ('items', versions.models.VersionedManyToManyField(to='pretixbase.Item', verbose_name='Products', help_text='This question will be asked to buyers of the selected products', related_name='questions', blank=True)),
            ],
            options={
                'verbose_name': 'Question',
                'verbose_name_plural': 'Questions',
            },
        ),
        migrations.CreateModel(
            name='QuestionAnswer',
            fields=[
                ('id', models.CharField(serialize=False, max_length=36, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(default=None, null=True, blank=True)),
                ('version_birth_date', models.DateTimeField()),
                ('answer', models.TextField()),
                ('cartposition', models.ForeignKey(blank=True, related_name='answers', null=True, to='pretixbase.CartPosition')),
                ('orderposition', models.ForeignKey(blank=True, related_name='answers', null=True, to='pretixbase.OrderPosition')),
                ('question', versions.models.VersionedForeignKey(related_name='answers', to='pretixbase.Question')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Quota',
            fields=[
                ('id', models.CharField(serialize=False, max_length=36, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(default=None, null=True, blank=True)),
                ('version_birth_date', models.DateTimeField()),
                ('name', models.CharField(verbose_name='Name', max_length=200)),
                ('size', models.PositiveIntegerField(verbose_name='Total capacity')),
                ('event', versions.models.VersionedForeignKey(verbose_name='Event', related_name='quotas', to='pretixbase.Event')),
                ('items', versions.models.VersionedManyToManyField(to='pretixbase.Item', verbose_name='Item', related_name='quotas', blank=True)),
                ('variations', pretix.base.models.VariationsField(to='pretixbase.ItemVariation', verbose_name='Variations', related_name='quotas', blank=True)),
            ],
            options={
                'verbose_name': 'Quota',
                'verbose_name_plural': 'Quotas',
            },
        ),
        migrations.AddField(
            model_name='organizer',
            name='permitted',
            field=models.ManyToManyField(related_name='organizers', to=settings.AUTH_USER_MODEL, through='pretixbase.OrganizerPermission'),
        ),
        migrations.AddField(
            model_name='itemvariation',
            name='values',
            field=versions.models.VersionedManyToManyField(related_name='variations', to='pretixbase.PropertyValue'),
        ),
        migrations.AddField(
            model_name='item',
            name='category',
            field=versions.models.VersionedForeignKey(verbose_name='Category', blank=True, to='pretixbase.ItemCategory', related_name='items', null=True, on_delete=django.db.models.deletion.PROTECT),
        ),
        migrations.AddField(
            model_name='item',
            name='event',
            field=versions.models.VersionedForeignKey(verbose_name='Event', related_name='items', to='pretixbase.Event', on_delete=django.db.models.deletion.PROTECT),
        ),
        migrations.AddField(
            model_name='event',
            name='organizer',
            field=versions.models.VersionedForeignKey(related_name='events', to='pretixbase.Organizer', on_delete=django.db.models.deletion.PROTECT),
        ),
        migrations.AddField(
            model_name='event',
            name='permitted',
            field=models.ManyToManyField(related_name='events', to=settings.AUTH_USER_MODEL, through='pretixbase.EventPermission'),
        ),
        migrations.AddField(
            model_name='cartposition',
            name='event',
            field=versions.models.VersionedForeignKey(verbose_name='Event', to='pretixbase.Event'),
        ),
        migrations.AddField(
            model_name='cartposition',
            name='item',
            field=versions.models.VersionedForeignKey(verbose_name='Item', to='pretixbase.Item'),
        ),
        migrations.AddField(
            model_name='cartposition',
            name='variation',
            field=versions.models.VersionedForeignKey(verbose_name='Variation', blank=True, null=True, to='pretixbase.ItemVariation'),
        ),
        migrations.AddField(
            model_name='cachedticket',
            name='order',
            field=versions.models.VersionedForeignKey(to='pretixbase.Order'),
        ),
    ]
