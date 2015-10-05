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
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('password', models.CharField(verbose_name='password', max_length=128)),
                ('last_login', models.DateTimeField(verbose_name='last login', blank=True, null=True)),
                ('is_superuser', models.BooleanField(verbose_name='superuser status', help_text='Designates that this user has all permissions without explicitly assigning them.', default=False)),
                ('email', models.EmailField(verbose_name='E-mail', null=True, unique=True, db_index=True, max_length=254, blank=True)),
                ('givenname', models.CharField(verbose_name='Given name', blank=True, null=True, max_length=255)),
                ('familyname', models.CharField(verbose_name='Family name', blank=True, null=True, max_length=255)),
                ('is_active', models.BooleanField(verbose_name='Is active', default=True)),
                ('is_staff', models.BooleanField(verbose_name='Is site admin', default=False)),
                ('date_joined', models.DateTimeField(verbose_name='Date joined', auto_now_add=True)),
                ('locale', models.CharField(verbose_name='Language', choices=[('en', 'English'), ('de', 'German'), ('de-informal', 'German (informal)')], default='en', max_length=50)),
                ('timezone', models.CharField(verbose_name='Timezone', default='UTC', max_length=100)),
                ('groups', models.ManyToManyField(verbose_name='groups', related_query_name='user', help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.', related_name='user_set', to='auth.Group', blank=True)),
                ('user_permissions', models.ManyToManyField(verbose_name='user permissions', related_query_name='user', help_text='Specific permissions for this user.', related_name='user_set', to='auth.Permission', blank=True)),
            ],
            options={
                'verbose_name_plural': 'Users',
                'verbose_name': 'User',
            },
        ),
        migrations.CreateModel(
            name='CachedFile',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, serialize=False)),
                ('expires', models.DateTimeField(blank=True, null=True)),
                ('date', models.DateTimeField(blank=True, null=True)),
                ('filename', models.CharField(max_length=255)),
                ('type', models.CharField(max_length=255)),
                ('file', models.FileField(upload_to=pretix.base.models.cachedfile_name, blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='CachedTicket',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('provider', models.CharField(max_length=255)),
                ('cachedfile', models.ForeignKey(to='pretixbase.CachedFile')),
            ],
        ),
        migrations.CreateModel(
            name='CartPosition',
            fields=[
                ('id', models.CharField(primary_key=True, serialize=False, max_length=36)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('session', models.CharField(verbose_name='Session', blank=True, null=True, max_length=255)),
                ('price', models.DecimalField(verbose_name='Price', max_digits=10, decimal_places=2)),
                ('datetime', models.DateTimeField(verbose_name='Date', auto_now_add=True)),
                ('expires', models.DateTimeField(verbose_name='Expiration date')),
                ('attendee_name', models.CharField(verbose_name='Attendee name', blank=True, help_text='Empty, if this product is not an admission ticket', null=True, max_length=255)),
            ],
            options={
                'verbose_name_plural': 'Cart positions',
                'verbose_name': 'Cart position',
            },
            bases=(pretix.base.models.ObjectWithAnswers, models.Model),
        ),
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.CharField(primary_key=True, serialize=False, max_length=36)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('name', pretix.base.i18n.I18nCharField(verbose_name='Name', max_length=200)),
                ('slug', models.SlugField(verbose_name='Slug', help_text='Should be short, only contain lowercase letters and numbers, and must be unique among your events. This is being used in addresses and bank transfer references.', validators=[django.core.validators.RegexValidator(message='The slug may only contain letters, numbers, dots and dashes.', regex='^[a-zA-Z0-9.-]+$')])),
                ('currency', models.CharField(verbose_name='Default currency', default='EUR', max_length=10)),
                ('date_from', models.DateTimeField(verbose_name='Event start time')),
                ('date_to', models.DateTimeField(verbose_name='Event end time', blank=True, null=True)),
                ('presale_end', models.DateTimeField(verbose_name='End of presale', blank=True, help_text='No products will be sold after this date.', null=True)),
                ('presale_start', models.DateTimeField(verbose_name='Start of presale', blank=True, help_text='No products will be sold before this date.', null=True)),
                ('plugins', models.TextField(verbose_name='Plugins', blank=True, null=True)),
            ],
            options={
                'verbose_name_plural': 'Events',
                'verbose_name': 'Event',
                'ordering': ('date_from', 'name'),
            },
        ),
        migrations.CreateModel(
            name='EventLock',
            fields=[
                ('event', models.CharField(primary_key=True, serialize=False, max_length=36)),
                ('date', models.DateTimeField(auto_now=True)),
                ('token', models.UUIDField(default=uuid.uuid4)),
            ],
        ),
        migrations.CreateModel(
            name='EventPermission',
            fields=[
                ('id', models.CharField(primary_key=True, serialize=False, max_length=36)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('can_change_settings', models.BooleanField(verbose_name='Can change event settings', default=True)),
                ('can_change_items', models.BooleanField(verbose_name='Can change product settings', default=True)),
                ('can_view_orders', models.BooleanField(verbose_name='Can view orders', default=True)),
                ('can_change_permissions', models.BooleanField(verbose_name='Can change permissions', default=True)),
                ('can_change_orders', models.BooleanField(verbose_name='Can change orders', default=True)),
                ('event', versions.models.VersionedForeignKey(to='pretixbase.Event')),
                ('user', models.ForeignKey(related_name='event_perms', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name_plural': 'Event permissions',
                'verbose_name': 'Event permission',
            },
        ),
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
                ('object', versions.models.VersionedForeignKey(related_name='setting_objects', to='pretixbase.Event')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Item',
            fields=[
                ('id', models.CharField(primary_key=True, serialize=False, max_length=36)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('name', pretix.base.i18n.I18nCharField(verbose_name='Item name', max_length=255)),
                ('active', models.BooleanField(verbose_name='Active', default=True)),
                ('description', pretix.base.i18n.I18nTextField(verbose_name='Description', blank=True, help_text='This is shown below the product name in lists.', null=True)),
                ('default_price', models.DecimalField(verbose_name='Default price', max_digits=7, null=True, decimal_places=2)),
                ('tax_rate', models.DecimalField(verbose_name='Taxes included in percent', blank=True, max_digits=7, null=True, decimal_places=2)),
                ('admission', models.BooleanField(verbose_name='Is an admission ticket', help_text='Whether or not buying this product allows a person to enter your event', default=False)),
                ('position', models.IntegerField(default=0)),
                ('picture', models.ImageField(upload_to=pretix.base.models.itempicture_upload_to, verbose_name='Product picture', blank=True, null=True)),
            ],
            options={
                'verbose_name_plural': 'Products',
                'verbose_name': 'Product',
                'ordering': ('category__position', 'category', 'position'),
            },
        ),
        migrations.CreateModel(
            name='ItemCategory',
            fields=[
                ('id', models.CharField(primary_key=True, serialize=False, max_length=36)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('name', pretix.base.i18n.I18nCharField(verbose_name='Category name', max_length=255)),
                ('position', models.IntegerField(default=0)),
                ('event', versions.models.VersionedForeignKey(related_name='categories', to='pretixbase.Event')),
            ],
            options={
                'verbose_name_plural': 'Product categories',
                'verbose_name': 'Product category',
                'ordering': ('position', 'version_birth_date'),
            },
        ),
        migrations.CreateModel(
            name='ItemVariation',
            fields=[
                ('id', models.CharField(primary_key=True, serialize=False, max_length=36)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('active', models.BooleanField(verbose_name='Active', default=True)),
                ('default_price', models.DecimalField(verbose_name='Default price', blank=True, max_digits=7, null=True, decimal_places=2)),
                ('item', versions.models.VersionedForeignKey(related_name='variations', to='pretixbase.Item')),
            ],
            options={
                'verbose_name_plural': 'Product variations',
                'verbose_name': 'Product variation',
            },
        ),
        migrations.CreateModel(
            name='Order',
            fields=[
                ('id', models.CharField(primary_key=True, serialize=False, max_length=36)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('code', models.CharField(verbose_name='Order code', max_length=16)),
                ('status', models.CharField(verbose_name='Status', choices=[('n', 'pending'), ('p', 'paid'), ('e', 'expired'), ('c', 'cancelled'), ('r', 'refunded')], max_length=3)),
                ('email', models.EmailField(verbose_name='E-mail', blank=True, null=True, max_length=254)),
                ('locale', models.CharField(verbose_name='Locale', blank=True, null=True, max_length=32)),
                ('secret', models.CharField(max_length=32, default=pretix.base.models.generate_secret)),
                ('datetime', models.DateTimeField(verbose_name='Date')),
                ('expires', models.DateTimeField(verbose_name='Expiration date')),
                ('payment_date', models.DateTimeField(verbose_name='Payment date', blank=True, null=True)),
                ('payment_provider', models.CharField(verbose_name='Payment provider', blank=True, null=True, max_length=255)),
                ('payment_fee', models.DecimalField(verbose_name='Payment method fee', max_digits=10, default=0, decimal_places=2)),
                ('payment_info', models.TextField(verbose_name='Payment information', blank=True, null=True)),
                ('payment_manual', models.BooleanField(verbose_name='Payment state was manually modified', default=False)),
                ('total', models.DecimalField(verbose_name='Total amount', max_digits=10, decimal_places=2)),
                ('event', versions.models.VersionedForeignKey(verbose_name='Event', related_name='orders', to='pretixbase.Event')),
            ],
            options={
                'verbose_name_plural': 'Orders',
                'verbose_name': 'Order',
                'ordering': ('-datetime',),
            },
        ),
        migrations.CreateModel(
            name='OrderPosition',
            fields=[
                ('id', models.CharField(primary_key=True, serialize=False, max_length=36)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('price', models.DecimalField(verbose_name='Price', max_digits=10, decimal_places=2)),
                ('attendee_name', models.CharField(verbose_name='Attendee name', blank=True, help_text='Empty, if this product is not an admission ticket', null=True, max_length=255)),
                ('item', versions.models.VersionedForeignKey(verbose_name='Item', related_name='positions', to='pretixbase.Item')),
                ('order', versions.models.VersionedForeignKey(verbose_name='Order', related_name='positions', to='pretixbase.Order')),
                ('variation', versions.models.VersionedForeignKey(verbose_name='Variation', to='pretixbase.ItemVariation', null=True, blank=True)),
            ],
            options={
                'verbose_name_plural': 'Order positions',
                'verbose_name': 'Order position',
            },
            bases=(pretix.base.models.ObjectWithAnswers, models.Model),
        ),
        migrations.CreateModel(
            name='Organizer',
            fields=[
                ('id', models.CharField(primary_key=True, serialize=False, max_length=36)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('name', models.CharField(verbose_name='Name', max_length=200)),
                ('slug', models.SlugField(verbose_name='Slug', help_text='Should be short, only contain lowercase letters and numbers, and must be unique among your events. This is being used in addresses and bank transfer references.', validators=[django.core.validators.RegexValidator(message='The slug may only contain letters, numbers, dots and dashes.', regex='^[a-zA-Z0-9.-]+$')])),
            ],
            options={
                'verbose_name_plural': 'Organizers',
                'verbose_name': 'Organizer',
                'ordering': ('name',),
            },
        ),
        migrations.CreateModel(
            name='OrganizerPermission',
            fields=[
                ('id', models.CharField(primary_key=True, serialize=False, max_length=36)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('can_create_events', models.BooleanField(verbose_name='Can create events', default=True)),
                ('organizer', versions.models.VersionedForeignKey(to='pretixbase.Organizer')),
                ('user', models.ForeignKey(related_name='organizer_perms', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name_plural': 'Organizer permissions',
                'verbose_name': 'Organizer permission',
            },
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
                ('object', versions.models.VersionedForeignKey(related_name='setting_objects', to='pretixbase.Organizer')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Property',
            fields=[
                ('id', models.CharField(primary_key=True, serialize=False, max_length=36)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('name', pretix.base.i18n.I18nCharField(verbose_name='Property name', max_length=250)),
                ('event', versions.models.VersionedForeignKey(related_name='properties', to='pretixbase.Event')),
            ],
            options={
                'verbose_name_plural': 'Product properties',
                'verbose_name': 'Product property',
            },
        ),
        migrations.CreateModel(
            name='PropertyValue',
            fields=[
                ('id', models.CharField(primary_key=True, serialize=False, max_length=36)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('value', pretix.base.i18n.I18nCharField(verbose_name='Value', max_length=250)),
                ('position', models.IntegerField(default=0)),
                ('prop', versions.models.VersionedForeignKey(related_name='values', to='pretixbase.Property')),
            ],
            options={
                'verbose_name_plural': 'Property values',
                'verbose_name': 'Property value',
                'ordering': ('position', 'version_birth_date'),
            },
        ),
        migrations.CreateModel(
            name='Question',
            fields=[
                ('id', models.CharField(primary_key=True, serialize=False, max_length=36)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('question', pretix.base.i18n.I18nTextField(verbose_name='Question')),
                ('type', models.CharField(verbose_name='Question type', choices=[('N', 'Number'), ('S', 'Text (one line)'), ('T', 'Multiline text'), ('B', 'Yes/No')], max_length=5)),
                ('required', models.BooleanField(verbose_name='Required question', default=False)),
                ('event', versions.models.VersionedForeignKey(related_name='questions', to='pretixbase.Event')),
                ('items', versions.models.VersionedManyToManyField(verbose_name='Products', blank=True, help_text='This question will be asked to buyers of the selected products', related_name='questions', to='pretixbase.Item')),
            ],
            options={
                'verbose_name_plural': 'Questions',
                'verbose_name': 'Question',
            },
        ),
        migrations.CreateModel(
            name='QuestionAnswer',
            fields=[
                ('id', models.CharField(primary_key=True, serialize=False, max_length=36)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('answer', models.TextField()),
                ('cartposition', models.ForeignKey(related_name='answers', to='pretixbase.CartPosition', null=True, blank=True)),
                ('orderposition', models.ForeignKey(related_name='answers', to='pretixbase.OrderPosition', null=True, blank=True)),
                ('question', versions.models.VersionedForeignKey(related_name='answers', to='pretixbase.Question')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Quota',
            fields=[
                ('id', models.CharField(primary_key=True, serialize=False, max_length=36)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('name', models.CharField(verbose_name='Name', max_length=200)),
                ('size', models.PositiveIntegerField(verbose_name='Total capacity')),
                ('event', versions.models.VersionedForeignKey(verbose_name='Event', related_name='quotas', to='pretixbase.Event')),
                ('items', versions.models.VersionedManyToManyField(verbose_name='Item', blank=True, related_name='quotas', to='pretixbase.Item')),
                ('variations', pretix.base.models.VariationsField(verbose_name='Variations', blank=True, related_name='quotas', to='pretixbase.ItemVariation')),
            ],
            options={
                'verbose_name_plural': 'Quotas',
                'verbose_name': 'Quota',
            },
        ),
        migrations.AddField(
            model_name='organizer',
            name='permitted',
            field=models.ManyToManyField(through='pretixbase.OrganizerPermission', related_name='organizers', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='itemvariation',
            name='values',
            field=versions.models.VersionedManyToManyField(related_name='variations', to='pretixbase.PropertyValue'),
        ),
        migrations.AddField(
            model_name='item',
            name='category',
            field=versions.models.VersionedForeignKey(verbose_name='Category', related_name='items', to='pretixbase.ItemCategory', null=True, blank=True, on_delete=django.db.models.deletion.PROTECT),
        ),
        migrations.AddField(
            model_name='item',
            name='event',
            field=versions.models.VersionedForeignKey(verbose_name='Event', related_name='items', to='pretixbase.Event', on_delete=django.db.models.deletion.PROTECT),
        ),
        migrations.AddField(
            model_name='item',
            name='properties',
            field=versions.models.VersionedManyToManyField(verbose_name='Properties', blank=True, help_text="The selected properties will be available for the user to select. After saving this field, move to the 'Variations' tab to configure the details.", related_name='items', to='pretixbase.Property'),
        ),
        migrations.AddField(
            model_name='event',
            name='organizer',
            field=versions.models.VersionedForeignKey(related_name='events', to='pretixbase.Organizer', on_delete=django.db.models.deletion.PROTECT),
        ),
        migrations.AddField(
            model_name='event',
            name='permitted',
            field=models.ManyToManyField(through='pretixbase.EventPermission', related_name='events', to=settings.AUTH_USER_MODEL),
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
            field=versions.models.VersionedForeignKey(verbose_name='Variation', to='pretixbase.ItemVariation', null=True, blank=True),
        ),
        migrations.AddField(
            model_name='cachedticket',
            name='order',
            field=versions.models.VersionedForeignKey(to='pretixbase.Order'),
        ),
    ]
