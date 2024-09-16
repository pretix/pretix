# Generated by Django 4.2.15 on 2024-09-16 15:10

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pretixbase", "0269_order_api_meta"),
    ]

    operations = [
        migrations.CreateModel(
            name="HistoricPassword",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("password", models.CharField(max_length=128)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="historic_passwords",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
