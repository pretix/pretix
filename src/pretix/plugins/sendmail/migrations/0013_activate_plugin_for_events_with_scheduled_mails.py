from django.db import migrations
from django.db.models import Exists, OuterRef


def activate_plugin(apps, schema_editor):
    Event = apps.get_model("pretixbase", "Event")
    ScheduledMail = apps.get_model("sendmail", "ScheduledMail")
    Rule = apps.get_model("sendmail", "Rule")

    events = (
        Event.objects
        .exclude(plugins__icontains="pretix.plugins.sendmail")
        .filter(
            Exists(
                ScheduledMail.objects.filter(event=OuterRef('pk'), rule__enabled=True).exclude(
                    state__in=['completed', 'missed'])
            )
        )
    )

    for event in events:
        plugins_active = event.plugins.split(',')
        plugins_active.append('pretix.plugins.sendmail')
        event.plugins = ','.join(plugins_active)
        event.save(update_fields=['plugins'])


class Migration(migrations.Migration):
    dependencies = [
        ("sendmail", "0012_remove_cross_event_scheduled_mails"),
    ]

    operations = [
        migrations.RunPython(activate_plugin),
    ]
