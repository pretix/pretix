#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General
# Public License, additional terms are applicable granting you additional
# permissions and placing additional restrictions on your usage of this
# software. Please refer to the pretix LICENSE file to obtain the full terms
# applicable to this work.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License
# for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#

"""
Martyn's Law compliance validation via OpenDQV.

Terrorism (Protection of Premises) Act 2025 requires event organisers to
document evacuation, invacuation, and lockdown procedures and brief all staff
before any event with 200+ expected attendance.

This module registers a ``pre_save`` signal on the pretix ``Event`` model
that validates compliance fields via OpenDQV's ``LocalValidator`` before a
qualifying event is saved.

Activation
----------
Set the environment variable ``ENABLE_OPENDQV_VALIDATION=true`` to enable
validation. The signal is registered regardless; it is a no-op unless the env
var is set and ``opendqv`` is installed.

The contract file (``contracts/pretix_event.yaml``, relative to the pretix
root or any path configured in ``OPENDQV_CONTRACTS_DIR``) must be present for
validation to run.

Named after Martyn Hett (1987–2017), killed in the Manchester Arena bombing on
22 May 2017.
"""

import os

from django.core.exceptions import ValidationError
from django.db.models.signals import pre_save
from django.dispatch import receiver


@receiver(pre_save, sender='pretixbase.Event')
def validate_martyns_law_compliance(sender, instance, **kwargs):
    """
    Pre-save signal that validates Martyn's Law compliance fields via OpenDQV
    when ``ENABLE_OPENDQV_VALIDATION=true`` and the event has 200+ expected
    attendance.

    Raises
    ------
    django.core.exceptions.ValidationError
        If any required compliance field is missing or invalid.
    """
    if not os.environ.get("ENABLE_OPENDQV_VALIDATION"):
        return

    expected = instance.expected_attendance
    if expected is None or expected < 200:
        return

    try:
        from opendqv.sdk.local import LocalValidator  # optional dependency
    except ImportError:
        return

    record = {
        "event_name": str(instance.name),
        "event_slug": instance.slug or "",
        "expected_attendance": expected,
        "duty_tier": instance.duty_tier or "",
        "evacuation_procedure_documented": (
            str(instance.evacuation_procedure_documented).lower()
            if instance.evacuation_procedure_documented is not None else ""
        ),
        "invacuation_procedure_documented": (
            str(instance.invacuation_procedure_documented).lower()
            if instance.invacuation_procedure_documented is not None else ""
        ),
        "lockdown_procedure_documented": (
            str(instance.lockdown_procedure_documented).lower()
            if instance.lockdown_procedure_documented is not None else ""
        ),
        "staff_briefing_completed": (
            str(instance.staff_briefing_completed).lower()
            if instance.staff_briefing_completed is not None else ""
        ),
        "staff_briefing_date": (
            instance.staff_briefing_date.isoformat()
            if instance.staff_briefing_date else ""
        ),
        "compliance_reviewed_by": instance.compliance_reviewed_by or "",
        "compliance_review_date": (
            instance.compliance_review_date.isoformat()
            if instance.compliance_review_date else ""
        ),
    }

    if instance.duty_tier == "enhanced":
        record.update({
            "senior_responsible_person": (
                instance.senior_responsible_person or ""
            ),
            "senior_responsible_person_role": (
                instance.senior_responsible_person_role or ""
            ),
            "sia_notification_reference": (
                instance.sia_notification_reference or ""
            ),
            "terrorism_protection_plan_documented": (
                str(instance.terrorism_protection_plan_documented).lower()
                if instance.terrorism_protection_plan_documented is not None
                else ""
            ),
            "terrorism_protection_plan_review_date": (
                instance.terrorism_protection_plan_review_date.isoformat()
                if instance.terrorism_protection_plan_review_date else ""
            ),
        })

    validator = LocalValidator()
    result = validator.validate(record, contract="pretix_event")

    if not result["valid"]:
        errors = "; ".join(
            "{}: {}".format(e["field"], e["message"])
            for e in result.get("errors", [])
        )
        raise ValidationError(
            "Martyn's Law compliance check failed: {}".format(errors)
        )
