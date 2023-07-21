from django.db import migrations

import pretix.base.models.fields


def migrate_status_rules(apps, schema_editor):
    rule_model = apps.get_model("sendmail", "Rule")
    for r in rule_model.objects.all():
        r.restrict_to_status = ['p', 'n__valid_if_pending']
        if r.include_pending:
            r.restrict_to_status.append('n__not_pending_approval_and_not_valid_if_pending')
        r.save()


class Migration(migrations.Migration):

    dependencies = [
        ('sendmail', '0003_rule_attach_ical'),
        ('pretixbase', '0241_itemmetaproperties_required_values'),
    ]

    operations = [
        migrations.AddField(
            model_name='rule',
            name='restrict_to_status',
            field=pretix.base.models.fields.MultiStringField(default=['p', 'n__valid_if_pending']),
        ),
        migrations.RunPython(migrate_status_rules),
        migrations.RemoveField(
            model_name='rule',
            name='include_pending',
        ),
    ]
