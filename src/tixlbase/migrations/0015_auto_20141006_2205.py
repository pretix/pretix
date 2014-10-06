# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tixlbase', '0014_auto_20141005_1037'),
    ]

    operations = [
        migrations.AlterField(
            model_name='item',
            name='questions',
            field=models.ManyToManyField(blank=True, related_name='items', verbose_name='Questions', help_text='The user will be asked to fill in answers for the selected questions', to='tixlbase.Question'),
        ),
        migrations.AlterField(
            model_name='question',
            name='event',
            field=models.ForeignKey(to='tixlbase.Event', related_name='questions'),
        ),
    ]
