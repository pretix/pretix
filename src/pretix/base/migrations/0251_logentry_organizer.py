# Generated by Django 4.2.4 on 2023-11-20 12:38

from django.db import migrations, models
import django.db.models.deletion
from django.db.models import F, Subquery, OuterRef


def backfill_organizer(apps, schema_editor):
    LogEntry = apps.get_model("pretixbase", "LogEntry")
    Event = apps.get_model("pretixbase", "Event")
    ContentType = apps.get_model("contenttypes", "ContentType")

    LogEntry.objects.filter(
        organizer_link__isnull=True, event__isnull=False
    ).update(organizer_link_id=Subquery(
            Event.objects.filter(pk=OuterRef('event_id')).values('organizer_id'),
        )
    )
    for ct in ContentType.objects.all():
        try:
            model = apps.get_model(ct.app_label, ct.model)
        except LookupError:
            continue
        if "organizer" in model._meta.fields:
            LogEntry.objects.filter(
                organizer_link__isnull=True, event__isnull=True, content_type=ct,
            ).update(
                organizer_link_id=Subquery(model.objects.filter(pk=OuterRef('object_id')).values('organizer_id'))
            )
        elif "event" in model._meta.fields:
            LogEntry.objects.filter(
                organizer_link__isnull=True, event__isnull=True, content_type=ct,
            ).update(
                organizer_link_id=Subquery(model.objects.filter(pk=OuterRef('object_id')).values('event__organizer_id'))
            )


class Migration(migrations.Migration):
    dependencies = [
        ("pretixbase", "0250_eventmetaproperty_filter_public"),
    ]

    operations = [
        migrations.AddField(
            model_name="logentry",
            name="organizer_link",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="pretixbase.organizer",
            ),
        ),
        migrations.RunPython(
            backfill_organizer,
        )
    ]
