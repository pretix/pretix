# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import pretix.base.i18n


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0023_auto_20150401_0954'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='name',
            field=pretix.base.i18n.I18nCharField(max_length=200, verbose_name='Name'),
        ),
        migrations.AlterField(
            model_name='item',
            name='long_description',
            field=pretix.base.i18n.I18nTextField(null=True, blank=True, verbose_name='Long description'),
        ),
        migrations.AlterField(
            model_name='item',
            name='name',
            field=pretix.base.i18n.I18nCharField(max_length=255, verbose_name='Item name'),
        ),
        migrations.AlterField(
            model_name='item',
            name='short_description',
            field=pretix.base.i18n.I18nTextField(null=True, blank=True, verbose_name='Short description', help_text='This is shown below the product name in lists.'),
        ),
        migrations.AlterField(
            model_name='property',
            name='name',
            field=pretix.base.i18n.I18nCharField(max_length=250, verbose_name='Property name'),
        ),
        migrations.AlterField(
            model_name='propertyvalue',
            name='value',
            field=pretix.base.i18n.I18nCharField(max_length=250, verbose_name='Value'),
        ),
        migrations.AlterField(
            model_name='question',
            name='question',
            field=pretix.base.i18n.I18nTextField(verbose_name='Question'),
        ),
    ]
