# Generated by Django 4.2.4 on 2024-01-11 15:56

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pretixbase", "0255_item_unavail_modes"),
    ]

    operations = [
        migrations.AddField(
            model_name="itemvariation",
            name="available_from_mode",
            field=models.CharField(default="hide", max_length=16),
        ),
        migrations.AddField(
            model_name="itemvariation",
            name="available_until_mode",
            field=models.CharField(default="hide", max_length=16),
        ),
    ]
