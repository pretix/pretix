# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import pretixbase.models
import versions.models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='itemcategory',
            options={'verbose_name_plural': 'Item categories', 'verbose_name': 'Item category', 'ordering': ('position', 'id')},
        ),
        migrations.RenameField(
            model_name='cartposition',
            old_name='total',
            new_name='price',
        ),
        migrations.AlterField(
            model_name='event',
            name='currency',
            field=models.CharField(verbose_name='Default currency', default='EUR', max_length=10),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='event',
            name='locale',
            field=models.CharField(verbose_name='Default locale', choices=[('de', 'German'), ('en', 'English')], default='en', max_length=10),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='questionanswer',
            unique_together=set([]),
        ),
    ]
