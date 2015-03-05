# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0013_merge'),
    ]

    operations = [
        migrations.RenameField(
            model_name='eventsetting',
            old_name='event',
            new_name='object',
        ),
        migrations.RenameField(
            model_name='organizersetting',
            old_name='organizer',
            new_name='object',
        ),
    ]
