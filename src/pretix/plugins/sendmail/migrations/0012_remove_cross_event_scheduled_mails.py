from django.db import migrations
from django.db.models import F


def remove_cross_event_scheduled_mails(apps, schema_editor):
    ScheduledMail = apps.get_model("sendmail", "ScheduledMail")
    ScheduledMail.objects.filter(subevent__isnull=False).exclude(subevent__event=F('rule__event')).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("sendmail", "0011_remove_cross_event_scheduled_mails"),
    ]

    operations = [
        migrations.RunPython(remove_cross_event_scheduled_mails),
    ]
