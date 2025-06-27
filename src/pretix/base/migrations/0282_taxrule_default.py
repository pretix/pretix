from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pretixbase", "0281_event_is_remote"),
    ]

    operations = [
        migrations.AddField(
            model_name="taxrule",
            name="default",
            field=models.BooleanField(default=False),
        ),
        migrations.AddConstraint(
            model_name="taxrule",
            constraint=models.UniqueConstraint(
                condition=models.Q(("default", True)),
                fields=("event",),
                name="one_default_per_event",
            ),
        ),
    ]
