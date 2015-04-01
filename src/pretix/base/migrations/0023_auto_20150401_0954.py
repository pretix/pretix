# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0022_auto_20150320_2239'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='event',
            name='locale',
        ),
        migrations.RemoveField(
            model_name='event',
            name='payment_term_days',
        ),
        migrations.RemoveField(
            model_name='event',
            name='payment_term_last',
        ),
        migrations.RemoveField(
            model_name='event',
            name='show_date_to',
        ),
        migrations.RemoveField(
            model_name='event',
            name='show_times',
        ),
        migrations.RemoveField(
            model_name='event',
            name='timezone',
        ),
    ]
