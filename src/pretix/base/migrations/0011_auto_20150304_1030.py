# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import versions.models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0010_auto_20150218_2048'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='orderposition',
            name='answers',
        ),
        migrations.AddField(
            model_name='cartposition',
            name='attendee_name',
            field=models.CharField(max_length=255, blank=True, null=True, verbose_name='Attendee name', help_text='Empty, if this item is not an admission ticket'),
        ),
        migrations.AddField(
            model_name='item',
            name='admission',
            field=models.BooleanField(verbose_name='Is a admission ticket', default=False, help_text='Whether or not this item allows a person to enter your event'),
        ),
        migrations.AddField(
            model_name='orderposition',
            name='attendee_name',
            field=models.CharField(max_length=255, blank=True, null=True, verbose_name='Attendee name', help_text='Empty, if this item is not an admission ticket'),
        ),
        migrations.AlterField(
            model_name='questionanswer',
            name='cartposition',
            field=models.ForeignKey(blank=True, to='pretixbase.CartPosition', null=True, related_name='answers'),
        ),
        migrations.AlterField(
            model_name='questionanswer',
            name='orderposition',
            field=models.ForeignKey(blank=True, to='pretixbase.OrderPosition', null=True, related_name='answers'),
        ),
        migrations.AlterField(
            model_name='questionanswer',
            name='question',
            field=versions.models.VersionedForeignKey(related_name='answers', to='pretixbase.Question'),
        ),
    ]
