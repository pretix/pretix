from django.db import migrations
from django.db.models import F


def remove_cross_event_scheduled_mails(apps, schema_editor):
    Rule = apps.get_model("sendmail", "Rule")
    ScheduledMail = apps.get_model("sendmail", "ScheduledMail")
    ScheduledMail.objects.filter(rule__subevent__isnull=False).exclude(rule__subevent__event=F('rule__event')).delete()
    Rule.objects.filter(subevent__isnull=False).exclude(subevent__event=F('event')).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("sendmail", "0010_auto_20250801_1342"),
    ]

    operations = [
        migrations.RunPython(remove_cross_event_scheduled_mails),
    ]
