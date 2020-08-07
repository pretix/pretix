from django.db import migrations


def migrate_change_allow_user_price(apps, schema_editor):
    # Previously, the "gt" value was meant to represent "greater or equal", which became an issue the moment
    # we introduced a "greater" and "greater or equal" option. This migrates any previous "greater or equal"
    # selection to the new "gte".
    Event_SettingsStore = apps.get_model('pretixbase', 'Event_SettingsStore')
    Event_SettingsStore.objects.filter(key="change_allow_user_price", value="gt").update(value="gte")


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0160_multiple_confirm_texts'),
    ]

    operations = [
        migrations.RunPython(migrate_change_allow_user_price, migrations.RunPython.noop),
    ]
