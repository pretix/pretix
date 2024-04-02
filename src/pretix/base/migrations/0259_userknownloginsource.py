# Generated by Django 4.2.10 on 2024-04-02 10:31

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import pretix.helpers.countries


class Migration(migrations.Migration):

    dependencies = [
        ("pretixbase", "0258_uniq_indx"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserKnownLoginSource",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("agent_type", models.CharField(max_length=255, null=True)),
                ("device_type", models.CharField(max_length=255, null=True)),
                ("os_type", models.CharField(max_length=255, null=True)),
                (
                    "country",
                    pretix.helpers.countries.FastCountryField(
                        countries=pretix.helpers.countries.CachedCountries,
                        max_length=2,
                        null=True,
                    ),
                ),
                ("last_seen", models.DateTimeField()),
            ],
        ),
        migrations.AddField(
            model_name="userknownloginsource",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="known_login_sources",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
