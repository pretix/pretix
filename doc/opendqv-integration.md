# OpenDQV Integration — Martyn's Law Compliance

This guide explains how to enable contract-driven Martyn's Law compliance
enforcement in pretix via [OpenDQV](https://github.com/OpenDQV/OpenDQV).

---

## What is Martyn's Law?

The **Terrorism (Protection of Premises) Act 2025** (commonly known as
Martyn's Law) requires event organisers and venue operators to:

- Document evacuation, invacuation (shelter-in-place), and lockdown procedures.
- Brief all staff on those procedures before the event opens.
- For events with 800+ expected attendance (**enhanced duty**): designate a
  Senior Responsible Person (SRP), notify the Security Industry Authority
  (SIA), and maintain a Terrorism Protection Plan.

The Act applies to any event or venue where **200 or more persons** are expected
to be present at the same time.

**Named after Martyn Hett (1987–2017)**, who was killed in the Manchester Arena
bombing on 22 May 2017. The Act exists because the emergency procedures that
could have saved lives were undocumented and untested at many public venues.

For official guidance: <https://www.legislation.gov.uk/ukpga/2025/14>
SIA guidance: <https://www.sia.homeoffice.gov.uk>

---

## New fields on the Event model

Fourteen nullable fields have been added to the pretix `Event` model:

### Standard duty (200–799 expected attendance)

| Field | Type | Description |
|-------|------|-------------|
| `expected_attendance` | `PositiveIntegerField` | Expected number of persons. Martyn's Law scope trigger: ≥ 200. |
| `duty_tier` | `CharField` | `standard` (200–799) or `enhanced` (800+) |
| `evacuation_procedure_documented` | `BooleanField` | Written evacuation procedure exists and is accessible to staff |
| `invacuation_procedure_documented` | `BooleanField` | Shelter-in-place procedure documented |
| `lockdown_procedure_documented` | `BooleanField` | Lockdown procedure documented |
| `staff_briefing_completed` | `BooleanField` | All staff briefed before the event opens |
| `staff_briefing_date` | `DateField` | Date the staff briefing was completed |

### Enhanced duty (800+ expected attendance)

| Field | Type | Description |
|-------|------|-------------|
| `senior_responsible_person` | `CharField(200)` | Full name of the designated SRP |
| `senior_responsible_person_role` | `CharField(200)` | SRP's role or job title |
| `sia_notification_reference` | `CharField(100)` | SIA notification reference number |
| `terrorism_protection_plan_documented` | `BooleanField` | Terrorism Protection Plan exists and is current |
| `terrorism_protection_plan_review_date` | `DateField` | Date the plan was last reviewed |

### Audit trail (all qualifying events)

| Field | Type | Description |
|-------|------|-------------|
| `compliance_reviewed_by` | `CharField(200)` | Name of the person who reviewed compliance |
| `compliance_review_date` | `DateField` | Date compliance was last reviewed |

All fields are `null=True, blank=True` — **existing events are unaffected**.

---

## Enabling validation

### 1. Install OpenDQV

```bash
pip install opendqv>=1.3.3
```

OpenDQV is an **optional dependency**. If it is not installed, the compliance
signal skips silently and pretix behaves as before.

### 2. Run the migration

```bash
python manage.py migrate
```

### 3. Enable validation

Set the environment variable:

```bash
ENABLE_OPENDQV_VALIDATION=true
```

Or in your Django settings / `.env` file:

```
ENABLE_OPENDQV_VALIDATION=true
```

Validation is **disabled by default** — setting the variable is required to
activate it.

### 4. Place the contract file

The contract file `contracts/pretix_event.yaml` is included in this repository.
OpenDQV will find it automatically if `OPENDQV_CONTRACTS_DIR` points to the
`contracts/` directory relative to your pretix installation root, or if you
copy it to your configured contracts directory.

```bash
# Example: copy to a custom contracts directory
cp contracts/pretix_event.yaml /path/to/your/contracts/
export OPENDQV_CONTRACTS_DIR=/path/to/your/contracts/
```

---

## How it works

A Django `pre_save` signal (`pretix/base/martyns_law.py`) fires every time an
`Event` is saved. It:

1. Checks whether `ENABLE_OPENDQV_VALIDATION=true` — if not set, returns
   immediately.
2. Checks `expected_attendance` — if `None` or `< 200`, returns immediately
   (event is not in scope).
3. Tries to import `opendqv.sdk.local.LocalValidator` — if not installed,
   returns silently.
4. Builds a compliance record from the event's fields.
5. Validates the record against the `pretix_event` contract using OpenDQV's
   `LocalValidator`.
6. If validation fails, raises `django.core.exceptions.ValidationError` with
   a human-readable, field-level error message. The save is blocked.

---

## Example: completing compliance for a qualifying event

```python
from pretix.base.models import Event
from django.utils import timezone

event = Event.objects.get(slug="my-conference")

# Fill in the Martyn's Law compliance fields
event.expected_attendance = 500
event.duty_tier = "standard"
event.evacuation_procedure_documented = True
event.invacuation_procedure_documented = True
event.lockdown_procedure_documented = True
event.staff_briefing_completed = True
event.staff_briefing_date = timezone.now().date()
event.compliance_reviewed_by = "Jane Smith, Safety Manager"
event.compliance_review_date = timezone.now().date()

event.save()  # Passes validation
```

For an enhanced-duty event (800+):

```python
event.expected_attendance = 1200
event.duty_tier = "enhanced"
# ... standard fields as above ...
event.senior_responsible_person = "John Doe"
event.senior_responsible_person_role = "Head of Security"
event.sia_notification_reference = "SIA-2025-123456"
event.terrorism_protection_plan_documented = True
event.terrorism_protection_plan_review_date = timezone.now().date()

event.save()  # Passes validation
```

---

## What happens if a field is missing?

With `ENABLE_OPENDQV_VALIDATION=true`, saving a qualifying event (200+) without
the required compliance fields raises a `ValidationError`:

```
ValidationError: Martyn's Law compliance check failed:
  duty_tier: duty_tier is required — declare 'standard' (200-799) or 'enhanced' (800+);
  evacuation_procedure_documented: evacuation_procedure_documented must be declared
  — required for all qualifying events under Martyn's Law
```

The error messages are field-level and human-readable. They reference the
specific Martyn's Law obligation that applies.

---

## Further reading

- [Terrorism (Protection of Premises) Act 2025](https://www.legislation.gov.uk/ukpga/2025/14)
- [SIA — Martyn's Law guidance](https://www.sia.homeoffice.gov.uk)
- [OpenDQV documentation](https://github.com/OpenDQV/OpenDQV)
- [OpenDQV SDK reference](https://github.com/OpenDQV/OpenDQV/blob/main/sdk/README.md)
