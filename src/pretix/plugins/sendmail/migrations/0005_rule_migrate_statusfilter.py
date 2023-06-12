from django.db import migrations


def migrate_status_rules(apps, schema_editor):
    rule_model = apps.get_model("sendmail", "Rule")
    for r in rule_model.objects.all():
        r.restrict_to_status = ['p', 'valid_if_pending']
        if r.include_pending:
            r.restrict_to_status.append('na')
        r.save()


class Migration(migrations.Migration):

    dependencies = [
        ('sendmail', '0004_rule_restrict_to_status'),
        ('pretixbase', '0241_itemmetaproperties_required_values'),
    ]

    operations = [
        migrations.RunPython(migrate_status_rules),
        migrations.RemoveField(
            model_name='rule',
            name='include_pending',
        ),
    ]
