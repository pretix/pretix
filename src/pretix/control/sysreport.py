#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
import os
import platform
import sys
import zoneinfo
from datetime import datetime, timedelta

from django.conf import settings
from django.db.models import Count, Exists, F, Min, OuterRef, Q, Sum
from django.utils.formats import date_format
from django.utils.timezone import now
from reportlab.lib import pagesizes
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from pretix import __version__
from pretix.base.models import Order, OrderPayment, Transaction
from pretix.base.plugins import get_all_plugins
from pretix.base.templatetags.money import money_filter
from pretix.plugins.reports.exporters import ReportlabExportMixin
from pretix.settings import DATA_DIR


class SysReport(ReportlabExportMixin):
    @property
    def pagesize(self):
        return pagesizes.portrait(pagesizes.A4)

    def __init__(self, start_month, tzname):
        self.tzname = tzname
        self.tz = zoneinfo.ZoneInfo(tzname)
        self.start_month = start_month

    def page_header(self, canvas, doc):
        pass

    def page_footer(self, canvas, doc):
        from reportlab.lib.units import mm

        canvas.setFont("OpenSans", 8)
        canvas.drawString(15 * mm, 10 * mm, "Page %d" % doc.page)
        canvas.drawRightString(
            self.pagesize[0] - doc.rightMargin,
            10 * mm,
            "Created: %s"
            % date_format(now().astimezone(self.tz), "SHORT_DATETIME_FORMAT"),
        )

    def render(self):
        return "sysreport.pdf", "application/pdf", self.create({})

    def get_story(self, doc, form_data):
        headlinestyle = self.get_style()
        headlinestyle.fontSize = 15
        subheadlinestyle = self.get_style()
        subheadlinestyle.fontSize = 13
        style_small = self.get_style()
        style_small.fontSize = 6

        story = [
            Paragraph("System report", headlinestyle),
            Spacer(1, 5 * mm),
            Paragraph("Usage", subheadlinestyle),
            Spacer(1, 5 * mm),
            self._usage_table(),
            Spacer(1, 5 * mm),
            Paragraph("Installed versions", subheadlinestyle),
            Spacer(1, 5 * mm),
            self._tech_table(),
            Spacer(1, 5 * mm),
            Paragraph("Plugins", subheadlinestyle),
            Spacer(1, 5 * mm),
            Paragraph(self._get_plugin_versions(), style_small),
            Spacer(1, 5 * mm),
            Paragraph("Custom templates", subheadlinestyle),
            Spacer(1, 5 * mm),
            Paragraph(self._get_custom_templates(), style_small),
            Spacer(1, 5 * mm),
        ]

        return story

    def _tech_table(self):
        style = self.get_style()
        style.fontSize = 8
        style_small = self.get_style()
        style_small.fontSize = 6

        w = self.pagesize[0] - 30 * mm
        colwidths = [
            a * w
            for a in (
                0.2,
                0.8,
            )
        ]
        tstyledata = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (0, -1), 0),
            ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
        ]
        tdata = [
            [Paragraph("Site URL:", style), Paragraph(settings.SITE_URL, style)],
            [Paragraph("pretix version:", style), Paragraph(__version__, style)],
            [Paragraph("Python version:", style), Paragraph(sys.version, style)],
            [Paragraph("Platform:", style), Paragraph(platform.platform(), style)],
            [
                Paragraph("Database engine:", style),
                Paragraph(settings.DATABASES["default"]["ENGINE"], style),
            ],
        ]
        table = Table(tdata, colWidths=colwidths, repeatRows=0)
        table.setStyle(TableStyle(tstyledata))
        return table

    def _usage_table(self):
        style = self.get_style()
        style.fontSize = 8
        style_small = self.get_style()
        style_small.fontSize = 6
        style_small.leading = 8
        style_small.alignment = TA_CENTER
        style_small_head = self.get_style()
        style_small_head.fontSize = 6
        style_small_head.leading = 8
        style_small_head.alignment = TA_CENTER
        style_small_head.fontName = "OpenSansBd"

        w = self.pagesize[0] - 30 * mm

        successful = (
            Q(status=Order.STATUS_PAID)
            | Q(valid_if_pending=True, status=Order.STATUS_PENDING)
            | Q(
                Exists(
                    OrderPayment.objects.filter(
                        order_id=OuterRef("pk"),
                        state__in=(
                            OrderPayment.PAYMENT_STATE_CONFIRMED,
                            OrderPayment.PAYMENT_STATE_REFUNDED,
                        ),
                    )
                ),
            )
        )
        orders_q = Order.objects.filter(
            successful,
            testmode=False,
        )
        orders_testmode_q = Order.objects.filter(
            testmode=True,
        )
        orders_unconfirmed_q = Order.objects.filter(
            ~successful,
            testmode=False,
        )
        revenue_q = Transaction.objects.filter(
            Exists(
                OrderPayment.objects.filter(
                    order_id=OuterRef("order_id"),
                    state__in=(
                        OrderPayment.PAYMENT_STATE_CONFIRMED,
                        OrderPayment.PAYMENT_STATE_REFUNDED,
                    ),
                )
            ),
            order__testmode=False,
        )

        currencies = sorted(
            list(
                set(
                    Transaction.objects.annotate(c=F("order__event__currency"))
                    .values_list("c", flat=True)
                    .distinct()
                )
            )
        )

        year_first = orders_q.aggregate(m=Min("datetime__year"))["m"]
        if not year_first:
            year_first = now().year
        elif datetime.now().month - 1 <= self.start_month:
            year_first -= 1
        year_last = now().year
        tdata = [
            [
                Paragraph(l, style_small_head)
                for l in (
                    "Time frame",
                    "Currency",
                    "Successful orders",
                    "Net revenue",
                    "Testmode orders",
                    "Unsucessful orders",
                    "Positions",
                    "Gross revenue",
                )
            ]
        ]

        for year in range(year_first, year_last + 1):
            for i, c in enumerate(currencies):
                first_day = datetime(
                    year, self.start_month, 1, 0, 0, 0, 0, tzinfo=self.tz
                )
                after_day = datetime(
                    year + 1, self.start_month, 1, 0, 0, 0, 0, tzinfo=self.tz
                )

                orders_count = (
                    orders_q.filter(
                        datetime__gte=first_day, datetime__lt=after_day
                    ).aggregate(c=Count("*"))["c"]
                    or 0
                )
                testmode_count = (
                    orders_testmode_q.filter(
                        datetime__gte=first_day, datetime__lt=after_day
                    ).aggregate(c=Count("*"))["c"]
                    or 0
                )
                unconfirmed_count = (
                    orders_unconfirmed_q.filter(
                        datetime__gte=first_day, datetime__lt=after_day
                    ).aggregate(c=Count("*"))["c"]
                    or 0
                )
                revenue_data = revenue_q.filter(
                    datetime__gte=first_day, datetime__lt=after_day, order__event__currency=c
                ).aggregate(
                    c=Sum("count"),
                    s_net=Sum(F("price") - F("tax_value")),
                    s_gross=Sum(F("price")),
                )

                tdata.append(
                    (
                        Paragraph(
                            date_format(first_day, "M Y")
                            + " – "
                            + date_format(after_day - timedelta(days=1), "M Y"),
                            style_small,
                        ),
                        Paragraph(c, style_small),
                        Paragraph(str(orders_count), style_small) if i == 0 else "",
                        Paragraph(money_filter(revenue_data.get("s_net") or 0, c), style_small),
                        Paragraph(str(testmode_count), style_small) if i == 0 else "",
                        Paragraph(str(unconfirmed_count), style_small) if i == 0 else "",
                        Paragraph(str(revenue_data.get("c") or 0), style_small),
                        Paragraph(money_filter(revenue_data.get("s_gross") or 0, c), style_small),
                    )
                )

        colwidths = [a * w for a in (0.18,) + (0.82 / 7,) * 7]
        tstyledata = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (0, -1), 0),
            ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]
        table = Table(tdata, colWidths=colwidths, repeatRows=0)
        table.setStyle(TableStyle(tstyledata))
        return table

    def _get_plugin_versions(self):
        lines = []
        for p in get_all_plugins():
            lines.append(f"{p.name} {p.version}")
        return ", ".join(lines)

    def _get_custom_templates(self):
        lines = []
        for dirpath, dirnames, filenames in os.walk(
            os.path.join(DATA_DIR, "templates")
        ):
            for f in filenames:
                lines.append(f"{dirpath}/{f}")

        d = "<br/>".join(lines[:50])
        if len(lines) > 50:
            d += "<br/>..."
        if not d:
            return "–"
        return d
