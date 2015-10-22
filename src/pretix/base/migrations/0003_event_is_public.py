# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0002_auto_20151021_1412'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='is_public',
            field=models.BooleanField(help_text="If selected, this event may show up on the ticket system's start page or an organization profile.", default=False, verbose_name='Visible in public lists'),
        ),
    ]
