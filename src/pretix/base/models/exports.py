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

from django.db import models
from django.utils.translation import gettext_lazy as _

from pretix.base.models import LoggedModel
from pretix.base.validators import RRuleValidator, multimail_validate


class ScheduledEventExport(LoggedModel):
    event = models.ForeignKey(
        "pretixbase.Event", on_delete=models.CASCADE, related_name="scheduled_exports"
    )
    export_identifier = models.CharField(
        max_length=190,
        verbose_name=_("Export"),
    )
    export_form_data = models.JSONField(default=dict)

    owner = models.ForeignKey(
        "pretixbase.User",
        on_delete=models.PROTECT,
        related_name="scheduled_event_exports",
    )

    mail_additional_recipients = models.TextField(
        verbose_name=_('Additional recipients'),
        null=False, blank=True, validators=[multimail_validate]
    )
    mail_additional_recipients_cc = models.TextField(
        verbose_name=_('Additional recipients (Cc)'),
        null=False, blank=True, validators=[multimail_validate]
    )
    mail_additional_recipients_bcc = models.TextField(
        verbose_name=_('Additional recipients (Bcc)'),
        null=False, blank=True, validators=[multimail_validate]
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
