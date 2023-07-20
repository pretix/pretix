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
from django.dispatch import receiver

from pretix.base.signals import (
    register_data_exporters, register_multievent_data_exporters,
)


@receiver(register_data_exporters, dispatch_uid="export_overview_report_pdf")
def register_report_pdf(sender, **kwargs):
    from .exporters import OverviewReport
    return OverviewReport


@receiver(register_data_exporters, dispatch_uid="export_overview_report_ordertaxlist")
def register_report_ordertaxlist(sender, **kwargs):
    from .exporters import OrderTaxListReport
    return OrderTaxListReport


@receiver(register_data_exporters, dispatch_uid="export_overview_report_ordertaxlistpdf")
def register_report_ordertaxlistpdf(sender, **kwargs):
    from .exporters import OrderTaxListReportPDF
    return OrderTaxListReportPDF


@receiver(register_data_exporters, dispatch_uid="export_accounting_report_pdf")
@receiver(register_multievent_data_exporters, dispatch_uid="multi_export_accounting_report_pdf")
def register_report_accounting_report_pdf(sender, **kwargs):
    from .accountingreport import ReportExporter
    return ReportExporter
