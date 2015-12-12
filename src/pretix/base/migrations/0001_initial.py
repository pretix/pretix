# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import uuid

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations, models

import pretix.base.i18n
import pretix.base.models.base
import pretix.base.models.items
import pretix.base.models.orders


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
        migrations.CreateModel(
            name='CachedFile',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('expires', models.DateTimeField(blank=True, null=True)),
                ('date', models.DateTimeField(blank=True, null=True)),
                ('filename', models.CharField(max_length=255)),
                ('type', models.CharField(max_length=255)),
                ('file', models.FileField(blank=True, null=True, upload_to=pretix.base.models.base.cachedfile_name)),
            ],
        ),
        migrations.CreateModel(
            name='CachedTicket',
            fields=[
                ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True, serialize=False)),
                ('provider', models.CharField(max_length=255)),
                ('cachedfile', models.ForeignKey(to='pretixbase.CachedFile')),
            ],
        ),
        migrations.CreateModel(
            name='CartPosition',
            fields=[
                ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True, serialize=False)),
                ('cart_id', models.CharField(verbose_name='Cart ID (e.g. session key)', max_length=255, blank=True, null=True)),
                ('price', models.DecimalField(verbose_name='Price', max_digits=10, decimal_places=2)),
                ('datetime', models.DateTimeField(verbose_name='Date', auto_now_add=True)),
                ('expires', models.DateTimeField(verbose_name='Expiration date')),
                ('attendee_name', models.CharField(verbose_name='Attendee name', max_length=255, blank=True, null=True, help_text='Empty, if this product is not an admission ticket')),
            ],
            options={
                'verbose_name': 'Cart position',
                'verbose_name_plural': 'Cart positions',
            },
            bases=(pretix.base.models.orders.ObjectWithAnswers, models.Model),
        ),
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True, serialize=False)),
                ('name', pretix.base.i18n.I18nCharField(verbose_name='Name', max_length=200)),
                ('slug', models.SlugField(verbose_name='Slug', validators=[django.core.validators.RegexValidator(message='The slug may only contain letters, numbers, dots and dashes.', regex='^[a-zA-Z0-9.-]+$')], help_text='Should be short, only contain lowercase letters and numbers, and must be unique among your events. This is being used in addresses and bank transfer references.')),
                ('currency', models.CharField(verbose_name='Default currency', default='EUR', max_length=10)),
                ('date_from', models.DateTimeField(verbose_name='Event start time')),
                ('date_to', models.DateTimeField(verbose_name='Event end time', blank=True, null=True)),
                ('is_public', models.BooleanField(verbose_name='Visible in public lists', default=False, help_text="If selected, this event may show up on the ticket system's start page or an organization profile.")),
                ('presale_end', models.DateTimeField(verbose_name='End of presale', help_text='No products will be sold after this date.', blank=True, null=True)),
                ('presale_start', models.DateTimeField(verbose_name='Start of presale', help_text='No products will be sold before this date.', blank=True, null=True)),
                ('plugins', models.TextField(verbose_name='Plugins', blank=True, null=True)),
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
                ('event', models.CharField(max_length=36, primary_key=True, serialize=False)),
                ('date', models.DateTimeField(auto_now=True)),
                ('token', models.UUIDField(default=uuid.uuid4)),
            ],
        ),
        migrations.CreateModel(
            name='EventPermission',
            fields=[
                ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True, serialize=False)),
                ('can_change_settings', models.BooleanField(verbose_name='Can change event settings', default=True)),
                ('can_change_items', models.BooleanField(verbose_name='Can change product settings', default=True)),
                ('can_view_orders', models.BooleanField(verbose_name='Can view orders', default=True)),
                ('can_change_permissions', models.BooleanField(verbose_name='Can change permissions', default=True)),
                ('can_change_orders', models.BooleanField(verbose_name='Can change orders', default=True)),
                ('event', models.ForeignKey(to='pretixbase.Event', related_name='user_perms')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, related_name='event_perms')),
            ],
            options={
                'verbose_name': 'Event permission',
                'verbose_name_plural': 'Event permissions',
            },
        ),
        migrations.CreateModel(
            name='EventSetting',
            fields=[
                ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True, serialize=False)),
                ('key', models.CharField(max_length=255)),
                ('value', models.TextField()),
                ('object', models.ForeignKey(to='pretixbase.Event', related_name='setting_objects')),
            ],
        ),
        migrations.CreateModel(
            name='Item',
            fields=[
                ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True, serialize=False)),
                ('name', pretix.base.i18n.I18nCharField(verbose_name='Item name', max_length=255)),
                ('active', models.BooleanField(verbose_name='Active', default=True)),
                ('description', pretix.base.i18n.I18nTextField(verbose_name='Description', help_text='This is shown below the product name in lists.', blank=True, null=True)),
                ('default_price', models.DecimalField(verbose_name='Default price', max_digits=7, decimal_places=2, null=True)),
                ('tax_rate', models.DecimalField(verbose_name='Taxes included in percent', max_digits=7, blank=True, null=True, decimal_places=2)),
                ('admission', models.BooleanField(verbose_name='Is an admission ticket', default=False, help_text='Whether or not buying this product allows a person to enter your event')),
                ('position', models.IntegerField(default=0)),
                ('picture', models.ImageField(verbose_name='Product picture', blank=True, null=True, upload_to=pretix.base.models.items.itempicture_upload_to)),
                ('available_from', models.DateTimeField(verbose_name='Available from', help_text='This product will not be sold before the given date.', blank=True, null=True)),
                ('available_until', models.DateTimeField(verbose_name='Available until', help_text='This product will not be sold after the given date.', blank=True, null=True)),
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
                ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True, serialize=False)),
                ('name', pretix.base.i18n.I18nCharField(verbose_name='Category name', max_length=255)),
                ('position', models.IntegerField(default=0)),
                ('event', models.ForeignKey(to='pretixbase.Event', related_name='categories')),
            ],
            options={
                'verbose_name': 'Product category',
                'verbose_name_plural': 'Product categories',
                'ordering': ('position', 'id'),
            },
        ),
        migrations.CreateModel(
            name='ItemVariation',
            fields=[
                ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True, serialize=False)),
                ('active', models.BooleanField(verbose_name='Active', default=True)),
                ('default_price', models.DecimalField(verbose_name='Default price', max_digits=7, blank=True, null=True, decimal_places=2)),
                ('item', models.ForeignKey(to='pretixbase.Item', related_name='variations')),
            ],
            options={
                'verbose_name': 'Product variation',
                'verbose_name_plural': 'Product variations',
            },
        ),
        migrations.CreateModel(
            name='Order',
            fields=[
                ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True, serialize=False)),
                ('code', models.CharField(verbose_name='Order code', max_length=16)),
                ('status', models.CharField(verbose_name='Status', max_length=3, choices=[('n', 'pending'), ('p', 'paid'), ('e', 'expired'), ('c', 'cancelled'), ('r', 'refunded')])),
                ('email', models.EmailField(verbose_name='E-mail', max_length=254, blank=True, null=True)),
                ('locale', models.CharField(verbose_name='Locale', max_length=32, blank=True, null=True)),
                ('secret', models.CharField(default=pretix.base.models.orders.generate_secret, max_length=32)),
                ('datetime', models.DateTimeField(verbose_name='Date')),
                ('expires', models.DateTimeField(verbose_name='Expiration date')),
                ('payment_date', models.DateTimeField(verbose_name='Payment date', blank=True, null=True)),
                ('payment_provider', models.CharField(verbose_name='Payment provider', max_length=255, blank=True, null=True)),
                ('payment_fee', models.DecimalField(verbose_name='Payment method fee', default=0, max_digits=10, decimal_places=2)),
                ('payment_info', models.TextField(verbose_name='Payment information', blank=True, null=True)),
                ('payment_manual', models.BooleanField(verbose_name='Payment state was manually modified', default=False)),
                ('total', models.DecimalField(verbose_name='Total amount', max_digits=10, decimal_places=2)),
                ('event', models.ForeignKey(to='pretixbase.Event', verbose_name='Event', related_name='orders')),
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
                ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True, serialize=False)),
                ('price', models.DecimalField(verbose_name='Price', max_digits=10, decimal_places=2)),
                ('attendee_name', models.CharField(verbose_name='Attendee name', max_length=255, blank=True, null=True, help_text='Empty, if this product is not an admission ticket')),
                ('item', models.ForeignKey(to='pretixbase.Item', on_delete=django.db.models.deletion.PROTECT, verbose_name='Item', related_name='positions')),
                ('order', models.ForeignKey(to='pretixbase.Order', on_delete=django.db.models.deletion.PROTECT, verbose_name='Order', related_name='positions')),
                ('variation', models.ForeignKey(blank=True, to='pretixbase.ItemVariation', on_delete=django.db.models.deletion.PROTECT, verbose_name='Variation', null=True)),
            ],
            options={
                'verbose_name': 'Order position',
                'verbose_name_plural': 'Order positions',
            },
            bases=(pretix.base.models.orders.ObjectWithAnswers, models.Model),
        ),
        migrations.CreateModel(
            name='Organizer',
            fields=[
                ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True, serialize=False)),
                ('name', models.CharField(verbose_name='Name', max_length=200)),
                ('slug', models.SlugField(verbose_name='Slug', validators=[django.core.validators.RegexValidator(message='The slug may only contain letters, numbers, dots and dashes.', regex='^[a-zA-Z0-9.-]+$')], help_text='Should be short, only contain lowercase letters and numbers, and must be unique among your events. This is being used in addresses and bank transfer references.')),
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
                ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True, serialize=False)),
                ('can_create_events', models.BooleanField(verbose_name='Can create events', default=True)),
                ('organizer', models.ForeignKey(to='pretixbase.Organizer', related_name='user_perms')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, related_name='organizer_perms')),
            ],
            options={
                'verbose_name': 'Organizer permission',
                'verbose_name_plural': 'Organizer permissions',
            },
        ),
        migrations.CreateModel(
            name='OrganizerSetting',
            fields=[
                ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True, serialize=False)),
                ('key', models.CharField(max_length=255)),
                ('value', models.TextField()),
                ('object', models.ForeignKey(to='pretixbase.Organizer', related_name='setting_objects')),
            ],
        ),
        migrations.CreateModel(
            name='Property',
            fields=[
                ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True, serialize=False)),
                ('name', pretix.base.i18n.I18nCharField(verbose_name='Property name', max_length=250)),
                ('event', models.ForeignKey(to='pretixbase.Event', related_name='properties')),
                ('item', models.ForeignKey(blank=True, to='pretixbase.Item', null=True, related_name='properties')),
            ],
            options={
                'verbose_name': 'Product property',
                'verbose_name_plural': 'Product properties',
            },
        ),
        migrations.CreateModel(
            name='PropertyValue',
            fields=[
                ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True, serialize=False)),
                ('value', pretix.base.i18n.I18nCharField(verbose_name='Value', max_length=250)),
                ('position', models.IntegerField(default=0)),
                ('prop', models.ForeignKey(to='pretixbase.Property', related_name='values')),
            ],
            options={
                'verbose_name': 'Property value',
                'verbose_name_plural': 'Property values',
                'ordering': ('position', 'id'),
            },
        ),
        migrations.CreateModel(
            name='Question',
            fields=[
                ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True, serialize=False)),
                ('question', pretix.base.i18n.I18nTextField(verbose_name='Question')),
                ('type', models.CharField(verbose_name='Question type', max_length=5, choices=[('N', 'Number'), ('S', 'Text (one line)'), ('T', 'Multiline text'), ('B', 'Yes/No')])),
                ('required', models.BooleanField(verbose_name='Required question', default=False)),
                ('event', models.ForeignKey(to='pretixbase.Event', related_name='questions')),
                ('items', models.ManyToManyField(verbose_name='Products', help_text='This question will be asked to buyers of the selected products', blank=True, to='pretixbase.Item', related_name='questions')),
            ],
            options={
                'verbose_name': 'Question',
                'verbose_name_plural': 'Questions',
            },
        ),
        migrations.CreateModel(
            name='QuestionAnswer',
            fields=[
                ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True, serialize=False)),
                ('answer', models.TextField()),
                ('cartposition', models.ForeignKey(blank=True, to='pretixbase.CartPosition', null=True, related_name='answers')),
                ('orderposition', models.ForeignKey(blank=True, to='pretixbase.OrderPosition', null=True, related_name='answers')),
                ('question', models.ForeignKey(to='pretixbase.Question', related_name='answers')),
            ],
        ),
        migrations.CreateModel(
            name='Quota',
            fields=[
                ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True, serialize=False)),
                ('name', models.CharField(verbose_name='Name', max_length=200)),
                ('size', models.PositiveIntegerField(verbose_name='Total capacity', help_text='Leave empty for an unlimited number of tickets.', blank=True, null=True)),
                ('event', models.ForeignKey(to='pretixbase.Event', verbose_name='Event', related_name='quotas')),
                ('items', models.ManyToManyField(verbose_name='Item', to='pretixbase.Item', blank=True, related_name='quotas')),
                ('variations', pretix.base.models.items.VariationsField(verbose_name='Variations', to='pretixbase.ItemVariation', blank=True, related_name='quotas')),
            ],
            options={
                'verbose_name': 'Quota',
                'verbose_name_plural': 'Quotas',
            },
        ),
        migrations.AddField(
            model_name='organizer',
            name='permitted',
            field=models.ManyToManyField(to=settings.AUTH_USER_MODEL, through='pretixbase.OrganizerPermission', related_name='organizers'),
        ),
        migrations.AddField(
            model_name='itemvariation',
            name='values',
            field=models.ForeignKey(to='pretixbase.PropertyValue', related_name='variations'),
        ),
        migrations.AddField(
            model_name='item',
            name='category',
            field=models.ForeignKey(blank=True, to='pretixbase.ItemCategory', on_delete=django.db.models.deletion.PROTECT, verbose_name='Category', null=True, related_name='items'),
        ),
        migrations.AddField(
            model_name='item',
            name='event',
            field=models.ForeignKey(to='pretixbase.Event', on_delete=django.db.models.deletion.PROTECT, verbose_name='Event', related_name='items'),
        ),
        migrations.AddField(
            model_name='event',
            name='organizer',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='pretixbase.Organizer', related_name='events'),
        ),
        migrations.AddField(
            model_name='event',
            name='permitted',
            field=models.ManyToManyField(to=settings.AUTH_USER_MODEL, through='pretixbase.EventPermission', related_name='events'),
        ),
        migrations.AddField(
            model_name='cartposition',
            name='event',
            field=models.ForeignKey(verbose_name='Event', to='pretixbase.Event'),
        ),
        migrations.AddField(
            model_name='cartposition',
            name='item',
            field=models.ForeignKey(verbose_name='Item', to='pretixbase.Item'),
        ),
        migrations.AddField(
            model_name='cartposition',
            name='variation',
            field=models.ForeignKey(blank=True, to='pretixbase.ItemVariation', verbose_name='Variation', null=True),
        ),
        migrations.AddField(
            model_name='cachedticket',
            name='order',
            field=models.ForeignKey(to='pretixbase.Order'),
        ),
        migrations.RunPython(initial_user),
    ]
