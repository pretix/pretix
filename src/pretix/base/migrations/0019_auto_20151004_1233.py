# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0018_eventlock_token'),
    ]

    operations = [
        migrations.RenameField(
            model_name='order',
            old_name='guest_email',
            new_name='email',
        ),
        migrations.RenameField(
            model_name='order',
            old_name='guest_locale',
            new_name='locale',
        ),
        migrations.RemoveField(
            model_name='cartposition',
            name='user',
        ),
        migrations.RemoveField(
            model_name='order',
            name='user',
        ),
    ]
