# Generated by Django 4.2.8 on 2024-03-24 17:43

import django.db.models.deletion
import i18nfield.fields
from django.db import migrations, models

import pretix.base.models.fields


class Migration(migrations.Migration):

    dependencies = [
        ("pretixbase", "0264_order_internal_secret"),
    ]

    operations = [
        migrations.CreateModel(
            name="SalesChannel",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("label", i18nfield.fields.I18nCharField(max_length=200)),
                ("identifier", models.CharField(max_length=200)),
                ("type", models.CharField(max_length=200)),
                ("position", models.PositiveIntegerField(default=0)),
                ("configuration", models.JSONField(default=dict)),
            ],
        ),
        migrations.RenameField(
            model_name="checkinlist",
            old_name="auto_checkin_sales_channels",
            new_name="auto_checkin_sales_channel_types",
        ),
        migrations.AddField(
            model_name="discount",
            name="all_sales_channels",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="event",
            name="all_sales_channels",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="item",
            name="all_sales_channels",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="itemvariation",
            name="all_sales_channels",
            field=models.BooleanField(default=True),
        ),
        migrations.RenameField(
            model_name="order",
            old_name="sales_channel",
            new_name="sales_channel_type",
        ),
        migrations.AddField(
            model_name="saleschannel",
            name="organizer",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="sales_channels",
                to="pretixbase.organizer",
            ),
        ),
        migrations.AddField(
            model_name="discount",
            name="limit_sales_channels",
            field=models.ManyToManyField(to="pretixbase.saleschannel"),
        ),
        migrations.AddField(
            model_name="event",
            name="limit_sales_channels",
            field=models.ManyToManyField(to="pretixbase.saleschannel"),
        ),
        migrations.AddField(
            model_name="item",
            name="limit_sales_channels",
            field=models.ManyToManyField(to="pretixbase.saleschannel"),
        ),
        migrations.AddField(
            model_name="itemvariation",
            name="limit_sales_channels",
            field=models.ManyToManyField(to="pretixbase.saleschannel"),
        ),
        migrations.AddField(
            model_name="checkinlist",
            name="auto_checkin_sales_channels",
            field=models.ManyToManyField(to="pretixbase.saleschannel"),
        ),
        migrations.AddField(
            model_name="order",
            name="sales_channel",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="pretixbase.saleschannel",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="saleschannel",
            unique_together={("organizer", "identifier")},
        ),
    ]
