# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0019_auto_20150314_1247'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='item',
            options={'verbose_name': 'Product', 'verbose_name_plural': 'Products'},
        ),
        migrations.AlterModelOptions(
            name='itemcategory',
            options={'ordering': ('position', 'id'), 'verbose_name': 'Product category', 'verbose_name_plural': 'Product categories'},
        ),
        migrations.AlterModelOptions(
            name='itemvariation',
            options={'verbose_name': 'Product variation', 'verbose_name_plural': 'Product variations'},
        ),
        migrations.AlterModelOptions(
            name='property',
            options={'verbose_name': 'Product property', 'verbose_name_plural': 'Product properties'},
        ),
        migrations.RemoveField(
            model_name='item',
            name='deleted',
        ),
        migrations.AlterField(
            model_name='cartposition',
            name='attendee_name',
            field=models.CharField(null=True, help_text='Empty, if this product is not an admission ticket', verbose_name='Attendee name', max_length=255, blank=True),
        ),
        migrations.AlterField(
            model_name='event',
            name='presale_end',
            field=models.DateTimeField(null=True, help_text='No products will be sold after this date.', verbose_name='End of presale', blank=True),
        ),
        migrations.AlterField(
            model_name='event',
            name='presale_start',
            field=models.DateTimeField(null=True, help_text='No products will be sold before this date.', verbose_name='Start of presale', blank=True),
        ),
        migrations.AlterField(
            model_name='eventpermission',
            name='can_change_items',
            field=models.BooleanField(default=True, verbose_name='Can change product settings'),
        ),
        migrations.AlterField(
            model_name='item',
            name='admission',
            field=models.BooleanField(default=False, help_text='Whether or not buying this product allows a person to enter your event', verbose_name='Is an admission ticket'),
        ),
        migrations.AlterField(
            model_name='item',
            name='short_description',
            field=models.TextField(null=True, help_text='This is shown below the product name in lists.', verbose_name='Short description', blank=True),
        ),
        migrations.AlterField(
            model_name='orderposition',
            name='attendee_name',
            field=models.CharField(null=True, help_text='Empty, if this product is not an admission ticket', verbose_name='Attendee name', max_length=255, blank=True),
        ),
        migrations.AlterField(
            model_name='organizer',
            name='slug',
            field=models.SlugField(verbose_name='Slug', unique=True),
        ),
    ]
