# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models

import pretix.base.i18n


class Migration(migrations.Migration):
    dependencies = [
        ('pretixbase', '0019_auto_20151004_1233'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='item',
            name='long_description',
        ),
        migrations.RenameField(
            model_name='item',
            old_name='short_description',
            new_name='description'
        ),
        migrations.AlterField(
            model_name='item',
            name='description',
            field=pretix.base.i18n.I18nTextField(null=True, verbose_name='Description', blank=True,
                                                 help_text='This is shown below the product name in lists.'),
        ),
    ]
