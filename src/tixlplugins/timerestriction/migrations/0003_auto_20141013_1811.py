# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('timerestriction', '0002_auto_20141013_1811'),
    ]

    operations = [
        migrations.RenameField(
            model_name='timerestriction',
            old_name='i',
            new_name='item',
        ),
    ]
