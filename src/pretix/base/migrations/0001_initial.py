# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.contrib.auth.hashers import make_password

from django.db import models, migrations
import pretix.base.models
import django.db.models.deletion
import pretix.base.i18n
import versions.models
import django.core.validators
from django.conf import settings


def initial_user(apps, schema_editor):
    User = apps.get_model("pretixbase", "User")
    user = User(identifier='admin@localhost', email='admin@localhost')
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
                ('id', models.AutoField(serialize=False, primary_key=True, auto_created=True, verbose_name='ID')),
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, verbose_name='last login', null=True)),
                ('is_superuser', models.BooleanField(default=False, help_text='Designates that this user has all permissions without explicitly assigning them.', verbose_name='superuser status')),
                ('identifier', models.CharField(max_length=255, unique=True)),
                ('username', models.CharField(max_length=120, blank=True, help_text='Letters, digits and ./+/-/_ only.', null=True)),
                ('email', models.EmailField(max_length=254, blank=True, verbose_name='E-mail', db_index=True, null=True)),
                ('givenname', models.CharField(max_length=255, blank=True, verbose_name='Given name', null=True)),
                ('familyname', models.CharField(max_length=255, blank=True, verbose_name='Family name', null=True)),
                ('is_active', models.BooleanField(default=True, verbose_name='Is active')),
                ('is_staff', models.BooleanField(default=False, verbose_name='Is site admin')),
                ('date_joined', models.DateTimeField(verbose_name='Date joined', auto_now_add=True)),
                ('locale', models.CharField(max_length=50, choices=[('en', 'English'), ('de', 'German')], default='en', verbose_name='Language')),
                ('timezone', models.CharField(max_length=100, default='UTC', verbose_name='Timezone')),
            ],
            options={
                'verbose_name_plural': 'Users',
                'verbose_name': 'User',
            },
        ),
        migrations.CreateModel(
            name='CartPosition',
            fields=[
                ('id', models.CharField(max_length=36, serialize=False, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('price', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Price')),
                ('datetime', models.DateTimeField(verbose_name='Date', auto_now_add=True)),
                ('expires', models.DateTimeField(verbose_name='Expiration date')),
                ('attendee_name', models.CharField(max_length=255, blank=True, verbose_name='Attendee name', help_text='Empty, if this product is not an admission ticket', null=True)),
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
                ('id', models.CharField(max_length=36, serialize=False, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('name', pretix.base.i18n.I18nCharField(max_length=200, verbose_name='Name')),
                ('slug', models.SlugField(validators=[django.core.validators.RegexValidator(regex='^[a-zA-Z0-9.-]+$', message='The slug may only contain letters, numbers, dots and dashes.')], help_text='Should be short, only contain lowercase letters and numbers, and must be unique among your events. This is being used in addresses and bank transfer references.', verbose_name='Slug')),
                ('currency', models.CharField(max_length=10, default='EUR', verbose_name='Default currency')),
                ('date_from', models.DateTimeField(verbose_name='Event start time')),
                ('date_to', models.DateTimeField(blank=True, verbose_name='Event end time', null=True)),
                ('presale_end', models.DateTimeField(blank=True, verbose_name='End of presale', help_text='No products will be sold after this date.', null=True)),
                ('presale_start', models.DateTimeField(blank=True, verbose_name='Start of presale', help_text='No products will be sold before this date.', null=True)),
                ('plugins', models.TextField(blank=True, verbose_name='Plugins', null=True)),
            ],
            options={
                'verbose_name_plural': 'Events',
                'ordering': ('date_from', 'name'),
                'verbose_name': 'Event',
            },
        ),
        migrations.CreateModel(
            name='EventPermission',
            fields=[
                ('id', models.CharField(max_length=36, serialize=False, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('can_change_settings', models.BooleanField(default=True, verbose_name='Can change event settings')),
                ('can_change_items', models.BooleanField(default=True, verbose_name='Can change product settings')),
                ('can_view_orders', models.BooleanField(default=True, verbose_name='Can view orders')),
                ('can_change_orders', models.BooleanField(default=True, verbose_name='Can change orders')),
                ('event', versions.models.VersionedForeignKey(to='pretixbase.Event')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, related_name='event_perms')),
            ],
            options={
                'verbose_name_plural': 'Event permissions',
                'verbose_name': 'Event permission',
            },
        ),
        migrations.CreateModel(
            name='EventSetting',
            fields=[
                ('id', models.CharField(max_length=36, serialize=False, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('key', models.CharField(max_length=255)),
                ('value', models.TextField()),
                ('object', versions.models.VersionedForeignKey(to='pretixbase.Event', related_name='setting_objects')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Item',
            fields=[
                ('id', models.CharField(max_length=36, serialize=False, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('name', pretix.base.i18n.I18nCharField(max_length=255, verbose_name='Item name')),
                ('active', models.BooleanField(default=True, verbose_name='Active')),
                ('short_description', pretix.base.i18n.I18nTextField(blank=True, verbose_name='Short description', help_text='This is shown below the product name in lists.', null=True)),
                ('long_description', pretix.base.i18n.I18nTextField(blank=True, verbose_name='Long description', null=True)),
                ('default_price', models.DecimalField(blank=True, verbose_name='Default price', max_digits=7, decimal_places=2, null=True)),
                ('tax_rate', models.DecimalField(blank=True, verbose_name='Taxes included in percent', max_digits=7, decimal_places=2, null=True)),
                ('admission', models.BooleanField(default=False, help_text='Whether or not buying this product allows a person to enter your event', verbose_name='Is an admission ticket')),
            ],
            options={
                'verbose_name_plural': 'Products',
                'verbose_name': 'Product',
            },
        ),
        migrations.CreateModel(
            name='ItemCategory',
            fields=[
                ('id', models.CharField(max_length=36, serialize=False, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('name', pretix.base.i18n.I18nCharField(max_length=255, verbose_name='Category name')),
                ('position', models.IntegerField(default=0)),
                ('event', versions.models.VersionedForeignKey(to='pretixbase.Event', related_name='categories')),
            ],
            options={
                'verbose_name_plural': 'Product categories',
                'ordering': ('position', 'id'),
                'verbose_name': 'Product category',
            },
        ),
        migrations.CreateModel(
            name='ItemVariation',
            fields=[
                ('id', models.CharField(max_length=36, serialize=False, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('active', models.BooleanField(default=True, verbose_name='Active')),
                ('default_price', models.DecimalField(blank=True, verbose_name='Default price', max_digits=7, decimal_places=2, null=True)),
                ('item', versions.models.VersionedForeignKey(to='pretixbase.Item', related_name='variations')),
            ],
            options={
                'verbose_name_plural': 'Product variations',
                'verbose_name': 'Product variation',
            },
        ),
        migrations.CreateModel(
            name='Order',
            fields=[
                ('id', models.CharField(max_length=36, serialize=False, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('code', models.CharField(max_length=16, verbose_name='Order code')),
                ('status', models.CharField(max_length=3, choices=[('n', 'pending'), ('p', 'paid'), ('e', 'expired'), ('c', 'cancelled'), ('r', 'refunded')], verbose_name='Status')),
                ('datetime', models.DateTimeField(verbose_name='Date')),
                ('expires', models.DateTimeField(verbose_name='Expiration date')),
                ('payment_date', models.DateTimeField(blank=True, verbose_name='Payment date', null=True)),
                ('payment_provider', models.CharField(max_length=255, blank=True, verbose_name='Payment provider', null=True)),
                ('payment_fee', models.DecimalField(decimal_places=2, max_digits=10, default=0, verbose_name='Payment method fee')),
                ('payment_info', models.TextField(blank=True, verbose_name='Payment information', null=True)),
                ('payment_manual', models.BooleanField(default=False, verbose_name='Payment state was manually modified')),
                ('total', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Total amount')),
                ('event', versions.models.VersionedForeignKey(to='pretixbase.Event', related_name='orders', verbose_name='Event')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, verbose_name='User', related_name='orders', blank=True, null=True)),
            ],
            options={
                'verbose_name_plural': 'Orders',
                'verbose_name': 'Order',
            },
        ),
        migrations.CreateModel(
            name='OrderPosition',
            fields=[
                ('id', models.CharField(max_length=36, serialize=False, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('price', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Price')),
                ('attendee_name', models.CharField(max_length=255, blank=True, verbose_name='Attendee name', help_text='Empty, if this product is not an admission ticket', null=True)),
                ('item', versions.models.VersionedForeignKey(to='pretixbase.Item', verbose_name='Item')),
                ('order', versions.models.VersionedForeignKey(to='pretixbase.Order', related_name='positions', verbose_name='Order')),
                ('variation', versions.models.VersionedForeignKey(to='pretixbase.ItemVariation', verbose_name='Variation', blank=True, null=True)),
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
                ('id', models.CharField(max_length=36, serialize=False, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('name', models.CharField(max_length=200, verbose_name='Name')),
                ('slug', models.SlugField(unique=True, verbose_name='Slug')),
            ],
            options={
                'verbose_name_plural': 'Organizers',
                'ordering': ('name',),
                'verbose_name': 'Organizer',
            },
        ),
        migrations.CreateModel(
            name='OrganizerPermission',
            fields=[
                ('id', models.CharField(max_length=36, serialize=False, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('can_create_events', models.BooleanField(default=True, verbose_name='Can create events')),
                ('organizer', versions.models.VersionedForeignKey(to='pretixbase.Organizer')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, related_name='organizer_perms')),
            ],
            options={
                'verbose_name_plural': 'Organizer permissions',
                'verbose_name': 'Organizer permission',
            },
        ),
        migrations.CreateModel(
            name='OrganizerSetting',
            fields=[
                ('id', models.CharField(max_length=36, serialize=False, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('key', models.CharField(max_length=255)),
                ('value', models.TextField()),
                ('object', versions.models.VersionedForeignKey(to='pretixbase.Organizer', related_name='setting_objects')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Property',
            fields=[
                ('id', models.CharField(max_length=36, serialize=False, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('name', pretix.base.i18n.I18nCharField(max_length=250, verbose_name='Property name')),
                ('event', versions.models.VersionedForeignKey(to='pretixbase.Event', related_name='properties')),
            ],
            options={
                'verbose_name_plural': 'Product properties',
                'verbose_name': 'Product property',
            },
        ),
        migrations.CreateModel(
            name='PropertyValue',
            fields=[
                ('id', models.CharField(max_length=36, serialize=False, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('value', pretix.base.i18n.I18nCharField(max_length=250, verbose_name='Value')),
                ('position', models.IntegerField(default=0)),
                ('prop', versions.models.VersionedForeignKey(to='pretixbase.Property', related_name='values')),
            ],
            options={
                'verbose_name_plural': 'Property values',
                'ordering': ('position',),
                'verbose_name': 'Property value',
            },
        ),
        migrations.CreateModel(
            name='Question',
            fields=[
                ('id', models.CharField(max_length=36, serialize=False, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('question', pretix.base.i18n.I18nTextField(verbose_name='Question')),
                ('type', models.CharField(max_length=5, choices=[('N', 'Number'), ('S', 'Text (one line)'), ('T', 'Multiline text'), ('B', 'Yes/No')], verbose_name='Question type')),
                ('required', models.BooleanField(default=False, verbose_name='Required question')),
                ('event', versions.models.VersionedForeignKey(to='pretixbase.Event', related_name='questions')),
            ],
            options={
                'verbose_name_plural': 'Questions',
                'verbose_name': 'Question',
            },
        ),
        migrations.CreateModel(
            name='QuestionAnswer',
            fields=[
                ('id', models.CharField(max_length=36, serialize=False, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('answer', models.TextField()),
                ('cartposition', models.ForeignKey(to='pretixbase.CartPosition', null=True, blank=True, related_name='answers')),
                ('orderposition', models.ForeignKey(to='pretixbase.OrderPosition', null=True, blank=True, related_name='answers')),
                ('question', versions.models.VersionedForeignKey(to='pretixbase.Question', related_name='answers')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Quota',
            fields=[
                ('id', models.CharField(max_length=36, serialize=False, primary_key=True)),
                ('identity', models.CharField(max_length=36)),
                ('version_start_date', models.DateTimeField()),
                ('version_end_date', models.DateTimeField(blank=True, default=None, null=True)),
                ('version_birth_date', models.DateTimeField()),
                ('name', models.CharField(max_length=200, verbose_name='Name')),
                ('size', models.PositiveIntegerField(verbose_name='Total capacity')),
                ('locked', models.DateTimeField(blank=True, null=True)),
                ('event', versions.models.VersionedForeignKey(to='pretixbase.Event', related_name='quotas', verbose_name='Event')),
                ('items', versions.models.VersionedManyToManyField(blank=True, related_name='quotas', to='pretixbase.Item', verbose_name='Item')),
                ('variations', pretix.base.models.VariationsField(blank=True, related_name='quotas', to='pretixbase.ItemVariation', verbose_name='Variations')),
            ],
            options={
                'verbose_name_plural': 'Quotas',
                'verbose_name': 'Quota',
            },
        ),
        migrations.AddField(
            model_name='organizer',
            name='permitted',
            field=models.ManyToManyField(through='pretixbase.OrganizerPermission', to=settings.AUTH_USER_MODEL, related_name='organizers'),
        ),
        migrations.AddField(
            model_name='itemvariation',
            name='values',
            field=versions.models.VersionedManyToManyField(to='pretixbase.PropertyValue', related_name='variations'),
        ),
        migrations.AddField(
            model_name='item',
            name='category',
            field=versions.models.VersionedForeignKey(on_delete=django.db.models.deletion.PROTECT, to='pretixbase.ItemCategory', verbose_name='Category', related_name='items', blank=True, null=True),
        ),
        migrations.AddField(
            model_name='item',
            name='event',
            field=versions.models.VersionedForeignKey(on_delete=django.db.models.deletion.PROTECT, to='pretixbase.Event', related_name='items', verbose_name='Event'),
        ),
        migrations.AddField(
            model_name='item',
            name='properties',
            field=versions.models.VersionedManyToManyField(blank=True, related_name='items', to='pretixbase.Property', help_text="The selected properties will be available for the user to select. After saving this field, move to the 'Variations' tab to configure the details.", verbose_name='Properties'),
        ),
        migrations.AddField(
            model_name='item',
            name='questions',
            field=versions.models.VersionedManyToManyField(blank=True, related_name='items', to='pretixbase.Question', help_text='The user will be asked to fill in answers for the selected questions', verbose_name='Questions'),
        ),
        migrations.AddField(
            model_name='event',
            name='organizer',
            field=versions.models.VersionedForeignKey(on_delete=django.db.models.deletion.PROTECT, to='pretixbase.Organizer', related_name='events'),
        ),
        migrations.AddField(
            model_name='event',
            name='permitted',
            field=models.ManyToManyField(through='pretixbase.EventPermission', to=settings.AUTH_USER_MODEL, related_name='events'),
        ),
        migrations.AddField(
            model_name='cartposition',
            name='event',
            field=versions.models.VersionedForeignKey(to='pretixbase.Event', verbose_name='Event'),
        ),
        migrations.AddField(
            model_name='cartposition',
            name='item',
            field=versions.models.VersionedForeignKey(to='pretixbase.Item', verbose_name='Item'),
        ),
        migrations.AddField(
            model_name='cartposition',
            name='user',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, verbose_name='User', blank=True, null=True),
        ),
        migrations.AddField(
            model_name='cartposition',
            name='variation',
            field=versions.models.VersionedForeignKey(to='pretixbase.ItemVariation', verbose_name='Variation', blank=True, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='event',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='pretixbase.Event', null=True, blank=True, related_name='users'),
        ),
        migrations.AddField(
            model_name='user',
            name='groups',
            field=models.ManyToManyField(to='auth.Group', help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.', related_name='user_set', blank=True, related_query_name='user', verbose_name='groups'),
        ),
        migrations.AddField(
            model_name='user',
            name='user_permissions',
            field=models.ManyToManyField(to='auth.Permission', help_text='Specific permissions for this user.', related_name='user_set', blank=True, related_query_name='user', verbose_name='user permissions'),
        ),
        migrations.AlterUniqueTogether(
            name='user',
            unique_together=set([('event', 'username')]),
        ),
        migrations.RunPython(initial_user),
    ]
