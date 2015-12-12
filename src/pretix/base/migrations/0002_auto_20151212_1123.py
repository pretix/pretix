# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='itemvariation',
            name='values',
        ),
        migrations.AddField(
            model_name='itemvariation',
            name='values',
            field=models.ManyToManyField(related_name='variations', to='pretixbase.PropertyValue'),
        ),
    ]
