from django.db import migrations

import pretix.base.models.fields


class Migration(migrations.Migration):

    dependencies = [
        ('sendmail', '0003_rule_attach_ical'),
    ]

    operations = [
        migrations.AddField(
            model_name='rule',
            name='restrict_to_status',
            field=pretix.base.models.fields.MultiStringField(default=['p', 'na', 'valid_if_pending']),
        ),
    ]
