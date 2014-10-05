# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tixlbase', '0013_propertyvalue_position'),
    ]

    operations = [
        migrations.CreateModel(
            name='Question',
            fields=[
                ('id', models.AutoField(primary_key=True, auto_created=True, verbose_name='ID', serialize=False)),
                ('question', models.TextField(verbose_name='Question')),
                ('type', models.CharField(choices=[('N', 'Number'), ('S', 'Text (one line)'), ('T', 'Multiline text'), ('B', 'Yes/No')], max_length=5, verbose_name='Question type')),
                ('required', models.BooleanField(default=False, verbose_name='Required question')),
                ('event', models.ForeignKey(to='tixlbase.Event', related_name='events')),
            ],
            options={
                'verbose_name': 'Question',
                'verbose_name_plural': 'Questions',
            },
            bases=(models.Model,),
        ),
        migrations.AlterModelOptions(
            name='itemvariation',
            options={'verbose_name': 'Item variation', 'verbose_name_plural': 'Item variations'},
        ),
        migrations.AlterModelOptions(
            name='propertyvalue',
            options={'ordering': ('position',), 'verbose_name': 'Property value', 'verbose_name_plural': 'Property values'},
        ),
        migrations.AddField(
            model_name='item',
            name='questions',
            field=models.ManyToManyField(to='tixlbase.Question', related_name='questions', blank=True, verbose_name='Questions', help_text='The user will be asked to fill in answers for the selected questions'),
            preserve_default=True,
        ),
    ]
