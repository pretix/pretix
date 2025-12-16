from django.db import migrations, models

from pretix.helpers.permission_migration import (
    OLD_TO_NEW_EVENT_MIGRATION, OLD_TO_NEW_ORGANIZER_MIGRATION,
)


def migrate_teams_forward(apps, schema_editor):
    Team = apps.get_model("pretixbase", "Team")

    for team in Team.objects.iterator():
        if all(getattr(team, k) for k in OLD_TO_NEW_EVENT_MIGRATION.keys() if k != "can_checkin_orders"):
            team.all_event_permissions = True
            team.limit_event_permissions = {}
        else:
            team.all_event_permissions = False
            for k, v in OLD_TO_NEW_EVENT_MIGRATION.items():
                if getattr(team, k):
                    team.limit_event_permissions.update({kk: True for kk in v})

        if all(getattr(team, k) for k in OLD_TO_NEW_ORGANIZER_MIGRATION.keys()):
            team.all_organizer_permissions = True
            team.limit_organizer_permissions = {}
        else:
            team.all_organizer_permissions = False
            for k, v in OLD_TO_NEW_ORGANIZER_MIGRATION.items():
                if getattr(team, k):
                    team.limit_organizer_permissions.update({kk: True for kk in v})

        team.save(update_fields=[
            "all_event_permissions", "limit_event_permissions", "all_organizer_permissions", "limit_organizer_permissions"
        ])


def migrate_teams_backward(apps, schema_editor):
    Team = apps.get_model("pretixbase", "Team")

    for team in Team.objects.iterator():
        for k, v in OLD_TO_NEW_EVENT_MIGRATION.items():
            setattr(team, k, team.all_event_permissions or all(team.limit_event_permissions.get(kk) for kk in v))
        for k, v in OLD_TO_NEW_ORGANIZER_MIGRATION.items():
            setattr(team, k, team.all_organizer_permissions or all(team.limit_organizer_permissions.get(kk) for kk in v))
        team.save()


class Migration(migrations.Migration):

    dependencies = [
        ("pretixbase", "0296_invoice_invoice_from_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="team",
            name="all_event_permissions",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="team",
            name="all_organizer_permissions",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="team",
            name="limit_event_permissions",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="team",
            name="limit_organizer_permissions",
            field=models.JSONField(default=dict),
        ),
        migrations.RunPython(
            migrate_teams_forward,
            migrate_teams_backward,
        ),
        migrations.RemoveField(
            model_name="team",
            name="can_change_event_settings",
        ),
        migrations.RemoveField(
            model_name="team",
            name="can_change_items",
        ),
        migrations.RemoveField(
            model_name="team",
            name="can_change_orders",
        ),
        migrations.RemoveField(
            model_name="team",
            name="can_change_organizer_settings",
        ),
        migrations.RemoveField(
            model_name="team",
            name="can_change_teams",
        ),
        migrations.RemoveField(
            model_name="team",
            name="can_change_vouchers",
        ),
        migrations.RemoveField(
            model_name="team",
            name="can_checkin_orders",
        ),
        migrations.RemoveField(
            model_name="team",
            name="can_create_events",
        ),
        migrations.RemoveField(
            model_name="team",
            name="can_manage_customers",
        ),
        migrations.RemoveField(
            model_name="team",
            name="can_manage_gift_cards",
        ),
        migrations.RemoveField(
            model_name="team",
            name="can_manage_reusable_media",
        ),
        migrations.RemoveField(
            model_name="team",
            name="can_view_orders",
        ),
        migrations.RemoveField(
            model_name="team",
            name="can_view_vouchers",
        ),
    ]
