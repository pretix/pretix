# Generated by Django 4.2.4 on 2023-08-29 15:31

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('sendmail', '0005_rule_checked_in_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='rule',
            name='subevent',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='pretixbase.subevent'),
        ),
        migrations.AlterField(
            model_name='rule',
            name='checked_in_status',
            field=models.CharField(default=None, max_length=10, null=True),
        ),
    ]
