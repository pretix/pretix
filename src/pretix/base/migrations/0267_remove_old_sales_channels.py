# Generated by Django 4.2.8 on 2024-03-25 13:34

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pretixbase", "0266_saleschannel_migrate_data"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="checkinlist",
            name="auto_checkin_sales_channel_types",
        ),
        migrations.RemoveField(
            model_name="discount",
            name="sales_channels",
        ),
        migrations.RemoveField(
            model_name="event",
            name="sales_channels",
        ),
        migrations.RemoveField(
            model_name="item",
            name="sales_channels",
        ),
        migrations.RemoveField(
            model_name="itemvariation",
            name="sales_channels",
        ),
        migrations.RemoveField(
            model_name="order",
            name="sales_channel_type",
        ),
        migrations.AlterField(
            model_name="order",
            name="sales_channel",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to="pretixbase.saleschannel",
            ),
        ),
    ]
