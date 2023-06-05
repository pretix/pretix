#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
import zoneinfo
from datetime import datetime, timedelta

from dateutil.rrule import rrulestr
from dateutil.tz import datetime_exists
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils.timezone import make_aware, now
from django.utils.translation import gettext_lazy as _

from pretix.base.models import LoggedModel
from pretix.base.validators import RRuleValidator, multimail_validate


class AbstractScheduledExport(LoggedModel):
    id = models.BigAutoField(primary_key=True)

    export_identifier = models.CharField(
        max_length=190,
        verbose_name=_("Export"),
    )
    export_form_data = models.JSONField(
        default=dict,
        encoder=DjangoJSONEncoder,
    )

    owner = models.ForeignKey(
        "pretixbase.User",
        on_delete=models.PROTECT,
    )
    locale = models.CharField(
        verbose_name=_('Language'),
        max_length=250
    )

    mail_additional_recipients = models.TextField(
        verbose_name=_('Additional recipients'),
        null=False, blank=True, validators=[multimail_validate],
        help_text=_("You can specify multiple recipients separated by commas.")
    )
    mail_additional_recipients_cc = models.TextField(
        verbose_name=_('Additional recipients (Cc)'),
        null=False, blank=True, validators=[multimail_validate],
        help_text=_("You can specify multiple recipients separated by commas.")
    )
    mail_additional_recipients_bcc = models.TextField(
        verbose_name=_('Additional recipients (Bcc)'),
        null=False, blank=True, validators=[multimail_validate],
        help_text=_("You can specify multiple recipients separated by commas.")
    )
    mail_subject = models.CharField(
        verbose_name=_('Subject'),
        max_length=250
    )
    mail_template = models.TextField(
        verbose_name=_('Message'),
    )

    schedule_rrule = models.TextField(
        null=True, blank=True, validators=[RRuleValidator()]
    )
    schedule_rrule_time = models.TimeField(
        verbose_name=_("Requested start time"),
        help_text=_("The actual start time might be delayed depending on system load."),
    )
    schedule_next_run = models.DateTimeField(null=True, blank=True)

    error_counter = models.IntegerField(default=0)
    error_last_message = models.TextField(null=True, blank=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.mail_subject

    def compute_next_run(self):
        tz = self.tz
        r = rrulestr(self.schedule_rrule)

        base_dt = now().astimezone(tz).replace(tzinfo=None)
        if now().astimezone(tz).time() < self.schedule_rrule_time:
            base_dt -= timedelta(days=1)

        new_d = r.after(base_dt, inc=False)
        if not new_d:
            self.schedule_next_run = None
            return

        self.schedule_next_run = make_aware(datetime.combine(new_d.date(), self.schedule_rrule_time), tz)
        if not datetime_exists(self.schedule_next_run):
            self.schedule_next_run += timedelta(hours=1)


class ScheduledEventExport(AbstractScheduledExport):
    event = models.ForeignKey(
        "pretixbase.Event", on_delete=models.CASCADE, related_name="scheduled_exports"
    )

    @property
    def tz(self):
        return self.event.timezone


class ScheduledOrganizerExport(AbstractScheduledExport):
    organizer = models.ForeignKey(
        "pretixbase.Organizer", on_delete=models.CASCADE, related_name="scheduled_exports"
    )
    timezone = models.CharField(max_length=100,
                                default=settings.TIME_ZONE,
                                verbose_name=_('Timezone'))

    @property
    def tz(self):
        return zoneinfo.ZoneInfo(self.timezone)
