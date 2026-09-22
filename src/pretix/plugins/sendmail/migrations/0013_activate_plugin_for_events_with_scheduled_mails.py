from django.db import migrations
from django.db.models import Exists, OuterRef


def activate_plugin(apps, schema_editor):
    Event = apps.get_model("pretixbase", "Event")
    ScheduledMail = apps.get_model("sendmail", "ScheduledMail")
    events = (
        Event.objects
        .exclude(plugins__icontains="pretix.plugins.sendmail")
        .filter(
            Exists(
                ScheduledMail.objects.filter(event=OuterRef('pk')).exclude(state=ScheduledMail.STATE_COMPLETED)
            )
        )
    )
    for event in events:
        event.enable_plugin('pretix.plugins.sendmail')
        event.save(update_fields=['plugins'])


class Migration(migrations.Migration):
    dependencies = [
        ("sendmail", "0012_remove_cross_event_scheduled_mails"),
    ]

    operations = [
        migrations.RunPython(activate_plugin),
    ]
