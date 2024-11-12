# Generated by Django 4.2.16 on 2024-11-12 10:46

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pretixbase", "0273_remove_checkinlist_auto_checkin_sales_channels"),
        ("pretixmultidomain", "0002_knowndomain_event"),
    ]

    operations = [
        migrations.CreateModel(
            name="AlternativeDomainAssignment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="knowndomain",
            name="mode",
            field=models.CharField(default="organizer", max_length=255),
        ),
        migrations.AlterField(
            model_name="knowndomain",
            name="event",
            field=models.OneToOneField(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="domain",
                to="pretixbase.event",
            ),
        ),
        migrations.AddConstraint(
            model_name="knowndomain",
            constraint=models.UniqueConstraint(
                condition=models.Q(("mode", "organizer")),
                fields=("organizer",),
                name="unique_organizer_domain",
            ),
        ),
        migrations.AddField(
            model_name="alternativedomainassignment",
            name="domain",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="event_assignments",
                to="pretixmultidomain.knowndomain",
            ),
        ),
        migrations.AddField(
            model_name="alternativedomainassignment",
            name="event",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="alternative_domain_assignment",
                to="pretixbase.event",
            ),
        ),
        migrations.RunSQL(
            sql="UPDATE pretixmultidomain_knowndomain SET mode = 'event' WHERE event_id IS NOT NULL",
            reverse_sql=migrations.RunSQL.noop,
        )
    ]
