# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0011_auto_20150304_1030'),
    ]

    operations = [
        migrations.AlterField(
            model_name='item',
            name='admission',
            field=models.BooleanField(verbose_name='Is an admission ticket', help_text='Whether or not this item allows a person to enter your event', default=False),
        ),
    ]
