# Generated migration — Martyn's Law (Terrorism (Protection of Premises) Act 2025)
# compliance fields on pretix Event model.
#
# All fields are nullable (null=True, blank=True) — zero breaking changes.
# Existing events are unaffected. Enable validation via ENABLE_OPENDQV_VALIDATION=true.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pretixbase", "0298_pluggable_permissions"),
    ]

    operations = [
        # Standard duty fields (qualifying events: 200+ expected attendance)
        migrations.AddField(
            model_name="event",
            name="expected_attendance",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="Expected attendance",
                help_text=(
                    "Expected number of persons attending. Martyn's Law applies "
                    "when this is 200 or more (Terrorism (Protection of Premises) "
                    "Act 2025)."
                ),
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="duty_tier",
            field=models.CharField(
                blank=True,
                null=True,
                max_length=20,
                choices=[
                    ("standard", "Standard duty (200–799 expected attendance)"),
                    ("enhanced", "Enhanced duty (800+ expected attendance)"),
                ],
                verbose_name="Martyn's Law duty tier",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="evacuation_procedure_documented",
            field=models.BooleanField(
                blank=True,
                null=True,
                verbose_name="Evacuation procedure documented",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="invacuation_procedure_documented",
            field=models.BooleanField(
                blank=True,
                null=True,
                verbose_name="Invacuation (shelter-in-place) procedure documented",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="lockdown_procedure_documented",
            field=models.BooleanField(
                blank=True,
                null=True,
                verbose_name="Lockdown procedure documented",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="staff_briefing_completed",
            field=models.BooleanField(
                blank=True,
                null=True,
                verbose_name="Staff briefing completed",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="staff_briefing_date",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="Staff briefing date",
            ),
        ),
        # Enhanced duty fields (800+ expected attendance)
        migrations.AddField(
            model_name="event",
            name="senior_responsible_person",
            field=models.CharField(
                blank=True,
                null=True,
                max_length=200,
                verbose_name="Senior responsible person (SRP)",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="senior_responsible_person_role",
            field=models.CharField(
                blank=True,
                null=True,
                max_length=200,
                verbose_name="Senior responsible person — role/job title",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="sia_notification_reference",
            field=models.CharField(
                blank=True,
                null=True,
                max_length=100,
                verbose_name="SIA notification reference",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="terrorism_protection_plan_documented",
            field=models.BooleanField(
                blank=True,
                null=True,
                verbose_name="Terrorism protection plan documented",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="terrorism_protection_plan_review_date",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="Terrorism protection plan — last review date",
            ),
        ),
        # Audit trail
        migrations.AddField(
            model_name="event",
            name="compliance_reviewed_by",
            field=models.CharField(
                blank=True,
                null=True,
                max_length=200,
                verbose_name="Compliance reviewed by",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="compliance_review_date",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="Compliance review date",
            ),
        ),
    ]
