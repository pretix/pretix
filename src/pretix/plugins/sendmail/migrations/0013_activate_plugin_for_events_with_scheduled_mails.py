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
        event.enable_plugin('pretix.plugins.sendmail')
        event.save(update_fields=['plugins'])

    only_completed_rules = Rule.objects.exclude(event__plugins__icontains="pretix.plugins.sendmail",
                                                enabled=False).filter(
        ~Exists(ScheduledMail.objects.filter(rule=OuterRef('pk')).exclude(state='completed'))
    )
    only_completed_rules.update(enabled=False)


class Migration(migrations.Migration):
    dependencies = [
        ("sendmail", "0012_remove_cross_event_scheduled_mails"),
    ]

    operations = [
        migrations.RunPython(activate_plugin),
    ]
