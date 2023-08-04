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
import copy
import datetime
import tempfile
from collections import OrderedDict, defaultdict
from decimal import Decimal

from django import forms
from django.db.models import F, Sum
from django.db.models.functions import Coalesce
from django.utils.formats import date_format, localize
from django.utils.html import escape
from django.utils.timezone import now
from django.utils.translation import gettext as _, gettext_lazy, pgettext_lazy
from reportlab.lib import colors, pagesizes
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

from pretix.base.exporter import BaseExporter
from pretix.base.models import (
    GiftCardTransaction, OrderFee, OrderPayment, OrderRefund, Transaction,
)
from pretix.base.templatetags.money import money_filter
from pretix.base.timeframes import (
    DateFrameField,
    resolve_timeframe_to_datetime_start_inclusive_end_exclusive,
)
from pretix.control.forms.filter import get_all_payment_providers
from pretix.plugins.reports.exporters import ReportlabExportMixin


class ReportExporter(ReportlabExportMixin, BaseExporter):
    pagesize = pagesizes.portrait(pagesizes.A4)
    identifier = "accountingreport"
    verbose_name = gettext_lazy("Accounting report")
    description = gettext_lazy(
        "Download a PDF report of all sales and payments within a given time frame."
    )
    category = pgettext_lazy("export_category", "Analysis")
    filename = "accountingreport"
    featured = True
    numbered_canvas = True

    @property
    def export_form_fields(self) -> dict:
        ff = OrderedDict(
            [
                (
                    "date_range",
                    DateFrameField(
                        label=_("Date range"),
                        include_future_frames=False,
                        required=False,
                    ),
                ),
                (
                    "no_testmode",
                    forms.BooleanField(
                        label=_("Ignore test mode orders"),
                        required=False,
                        initial=True,
                    ),
                ),
                (
                    "split_subevents",
                    forms.BooleanField(
                        label=_("Split event series by date"),
                        required=False,
                        initial=False,
                    ),
                ),
            ]
        )
        if not self.is_multievent and not self.event.has_subevents:
            del ff["split_subevents"]
        return ff

    def describe_filters(self, form_data: dict):
        filters = []
        if self.is_multievent and self.events.count() == self.organizer.events.count():
            filters.append(_("Events") + ": " + _("All"))
        elif self.is_multievent:
            filters.append(
                _("Events") + ": " + ", ".join(str(i.name) for i in self.events)
            )
        else:
            filters.append(
                f'{_("Event")}: {self.event.name} ({self.event.get_date_range_display()})'
            )

        if form_data["date_range"]:
            dt_start, df_end = resolve_timeframe_to_datetime_start_inclusive_end_exclusive(
                now(), form_data["date_range"], self.timezone
            )
            if dt_start:
                filters.append(
                    _("Begin")
                    + ": "
                    + date_format(
                        dt_start.astimezone(self.timezone), "SHORT_DATETIME_FORMAT"
                    )
                )
            if df_end:
                filters.append(
                    _("End")
                    + ": "
                    + date_format(
                        (df_end - datetime.timedelta.resolution).astimezone(
                            self.timezone
                        ),
                        "SHORT_DATETIME_FORMAT",
                    )
                )

        if not form_data["no_testmode"]:
            filters.append(_("Report includes test orders which may be deleted later!"))

        if self._transaction_qs(form_data, currency=None).filter(migrated=True).exists():
            filters.append(
                _(
                    "The report time frame includes data generated with an old software version that did not yet "
                    "store all data required to create this report. The report might therefore be inaccurate "
                    "with regards to orders that were changed in the time frame."
                )
            )

        return filters

    def _giftcard_transaction_qs(self, form_data, currency, ignore_dates=False):
        qs = GiftCardTransaction.objects.filter(
            card__issuer=self.organizer,
            card__currency=currency,
        )
        if form_data["date_range"] and not ignore_dates:
            df_start, df_end = resolve_timeframe_to_datetime_start_inclusive_end_exclusive(
                now(), form_data["date_range"], self.timezone
            )
            if df_start:
                qs = qs.filter(datetime__gte=df_start)
            if df_end:
                qs = qs.filter(datetime__lt=df_end)
        if form_data["no_testmode"]:
            qs = qs.filter(card__testmode=False)
        return qs

    def _transaction_qs(self, form_data, currency, ignore_dates=False):
        qs = Transaction.objects.filter(
            order__event__in=self.events,
        )
        if currency is not None:
            qs = qs.filter(
                order__event__currency=currency,
            )
        if form_data["date_range"] and not ignore_dates:
            df_start, df_end = resolve_timeframe_to_datetime_start_inclusive_end_exclusive(
                now(), form_data["date_range"], self.timezone
            )
            if df_start:
                qs = qs.filter(datetime__gte=df_start)
            if df_end:
                qs = qs.filter(datetime__lt=df_end)
        if form_data["no_testmode"]:
            qs = qs.filter(order__testmode=False)
        return qs

    def _payment_qs(self, form_data, currency, ignore_dates=False):
        qs = OrderPayment.objects.filter(
            order__event__in=self.events,
            order__event__currency=currency,
            state__in=(
                OrderPayment.PAYMENT_STATE_CONFIRMED,
                OrderPayment.PAYMENT_STATE_REFUNDED,
            ),
        )
        if form_data["date_range"] and not ignore_dates:
            (
                df_start,
                df_end,
            ) = resolve_timeframe_to_datetime_start_inclusive_end_exclusive(
                now(), form_data["date_range"], self.timezone
            )
            if df_start:
                qs = qs.filter(payment_date__gte=df_start)
            if df_end:
                qs = qs.filter(payment_date__lt=df_end)
        if form_data["no_testmode"]:
            qs = qs.filter(order__testmode=False)
        return qs

    def _refund_qs(self, form_data, currency, ignore_dates=False):
        qs = OrderRefund.objects.filter(
            order__event__in=self.events,
            order__event__currency=currency,
            state=OrderRefund.REFUND_STATE_DONE,
        )
        if form_data["date_range"] and not ignore_dates:
            df_start, df_end = resolve_timeframe_to_datetime_start_inclusive_end_exclusive(
                now(), form_data["date_range"], self.timezone
            )
            if df_start:
                qs = qs.filter(execution_date__gte=df_start)
            if df_end:
                qs = qs.filter(execution_date__lt=df_end)
        if form_data["no_testmode"]:
            qs = qs.filter(order__testmode=False)
        return qs

    def _transaction_qs_group(self, qs, form_data):
        subevent_values = {}
        subevent_order_by = {}
        if form_data.get("split_subevents"):
            subevent_values = {"subevent_id", "subevent__name", "subevent__date_from"}
            subevent_order_by = {Coalesce(F("subevent__date_from"), F("order__event__date_from")), Coalesce(F("subevent_id"), F("order__event_id"))}

        qs = qs.order_by(
            *subevent_order_by,
            "order__event__date_from",
            "order__event__slug",
            F("fee_type").asc(nulls_first=True),
            F("internal_type").asc(nulls_first=True),
            F("item__category__position").asc(nulls_first=True),
            F("item__category_id").asc(nulls_first=True),
            F("item__position").asc(nulls_last=True),
            "item_id",
            "variation__position",
            "variation_id",
            "price",
            "tax_rate",
        ).values(
            *subevent_values,
            "order__event__date_from",
            "order__event__slug",
            "order__event__name",
            "item_id",
            "item__internal_name",
            "item__name",
            "variation__value",
            "variation_id",
            "fee_type",
            "internal_type",
            "price",
            "tax_rate",
        )
        return qs

    def _transaction_group_header_label(self):
        return _("Event") + " / " + _("Product")

    def _transaction_group_label(self, form_data, r):
        if not self.is_multievent and not form_data.get("split_subevents"):
            return None
        if r.get("subevent_id"):
            return "{} - {} ({}) [{}]".format(
                r["order__event__name"],
                r["subevent__name"],
                date_format(r["subevent__date_from"]),
                r["order__event__slug"]
            )
        else:
            return "{} [{}]".format(r["order__event__name"], r["order__event__slug"])

    def _transaction_row_label(self, r):
        if r["item_id"]:
            if r["variation_id"]:
                return f'{r["item__internal_name"] or r["item__name"]} - {r["variation__value"]}'
            else:
                return str(r["item__internal_name"] or r["item__name"])
        elif r["fee_type"]:
            fee_types = dict(OrderFee.FEE_TYPES)
            if r["internal_type"]:
                return f'{fee_types.get(r["fee_type"], r["fee_type"])} - {r["internal_type"]}'
            else:
                return fee_types.get(r["fee_type"], r["fee_type"])
        else:
            return "?"

    def _table_transactions(self, form_data, currency):
        tstyle = copy.copy(self.get_style())
        tstyle.fontSize = 8
        tstyle.leading = 10
        tstyle_right = copy.copy(tstyle)
        tstyle_right.alignment = TA_RIGHT
        tstyle_bold = copy.copy(tstyle)
        tstyle_bold.fontName = "OpenSansBd"
        tstyle_bold_right = copy.copy(tstyle_bold)
        tstyle_bold_right.alignment = TA_RIGHT

        tdata = [
            [
                Paragraph(self._transaction_group_header_label(), tstyle_bold),
                Paragraph(_("Price"), tstyle_bold_right),
                Paragraph(_("Tax rate"), tstyle_bold_right),
                Paragraph("#", tstyle_bold_right),
                Paragraph(_("Net total"), tstyle_bold_right),
                Paragraph(_("Tax total"), tstyle_bold_right),
                Paragraph(_("Gross total"), tstyle_bold_right),
            ]
        ]

        qs = (
            self._transaction_qs_group(
                self._transaction_qs(form_data, currency),
                form_data
            )
            .annotate(
                sum_cont=Sum("count"),
                sum_price=Sum(F("count") * F("price")),
                sum_tax=Sum(F("count") * F("tax_value")),
            )
        )

        tstyledata = []

        sum_cnt_by_tax_rate = defaultdict(int)
        sum_price_by_tax_rate = defaultdict(Decimal)
        sum_tax_by_tax_rate = defaultdict(Decimal)
        sum_price_by_group = Decimal("0.00")
        sum_tax_by_group = Decimal("0.00")
        last_group = None
        last_group_head_idx = 0
        for r in qs:
            e = self._transaction_group_label(form_data, r)

            if e != last_group:
                if last_group_head_idx > 0 and e is not None:
                    tdata[last_group_head_idx][4] = Paragraph(money_filter(sum_price_by_group - sum_tax_by_group, currency), tstyle_bold_right),
                    tdata[last_group_head_idx][5] = Paragraph(money_filter(sum_tax_by_group, currency), tstyle_bold_right),
                    tdata[last_group_head_idx][6] = Paragraph(money_filter(sum_price_by_group, currency), tstyle_bold_right),
                tdata.append(
                    [
                        Paragraph(
                            e,
                            tstyle_bold,
                        ),
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                    ]
                )
                tstyledata.append(
                    ("SPAN", (0, len(tdata) - 1), (3, len(tdata) - 1)),
                )
                last_group = e
                last_group_head_idx = len(tdata) - 1
                sum_price_by_group = Decimal("0.00")
                sum_tax_by_group = Decimal("0.00")

            text = self._transaction_row_label(r)
            tdata.append(
                [
                    Paragraph(text, tstyle),
                    Paragraph(
                        money_filter(r["price"], currency)
                        if "price" in r and r["price"] is not None
                        else "",
                        tstyle_right,
                    ),
                    Paragraph(localize(r["tax_rate"].normalize()) + " %", tstyle_right),
                    Paragraph(str(r["sum_cont"]), tstyle_right),
                    Paragraph(
                        money_filter(r["sum_price"] - r["sum_tax"], currency), tstyle_right
                    ),
                    Paragraph(money_filter(r["sum_tax"], currency), tstyle_right),
                    Paragraph(money_filter(r["sum_price"], currency), tstyle_right),
                ]
            )
            sum_cnt_by_tax_rate[r["tax_rate"]] += r["sum_cont"]
            sum_price_by_tax_rate[r["tax_rate"]] += r["sum_price"]
            sum_tax_by_tax_rate[r["tax_rate"]] += r["sum_tax"]
            sum_price_by_group += r["sum_price"]
            sum_tax_by_group += r["sum_tax"]

        if last_group_head_idx > 0 and last_group is not None:
            tdata[last_group_head_idx][4] = Paragraph(money_filter(sum_price_by_group - sum_tax_by_group, currency), tstyle_bold_right),
            tdata[last_group_head_idx][5] = Paragraph(money_filter(sum_tax_by_group, currency), tstyle_bold_right),
            tdata[last_group_head_idx][6] = Paragraph(money_filter(sum_price_by_group, currency), tstyle_bold_right),

        if len(sum_tax_by_tax_rate) > 1:
            for tax_rate in sorted(sum_tax_by_tax_rate.keys(), reverse=True):
                tdata.append(
                    [
                        Paragraph(_("Sum"), tstyle),
                        Paragraph("", tstyle_right),
                        Paragraph(localize(tax_rate.normalize()) + " %", tstyle_right),
                        Paragraph("", tstyle_right),
                        Paragraph(
                            money_filter(
                                sum_price_by_tax_rate[tax_rate]
                                - sum_tax_by_tax_rate[tax_rate],
                                currency,
                            ),
                            tstyle_right,
                        ),
                        Paragraph(
                            money_filter(sum_tax_by_tax_rate[tax_rate], currency), tstyle_right
                        ),
                        Paragraph(
                            money_filter(sum_price_by_tax_rate[tax_rate], currency),
                            tstyle_right,
                        ),
                    ]
                )
            tstyledata += [
                (
                    "LINEABOVE",
                    (0, -len(sum_tax_by_tax_rate) - 1),
                    (-1, -len(sum_tax_by_tax_rate) - 1),
                    0.5,
                    colors.black,
                ),
            ]

        tdata.append(
            [
                Paragraph(_("Sum"), tstyle_bold),
                Paragraph("", tstyle_right),
                Paragraph("", tstyle_right),
                Paragraph("", tstyle_bold_right),
                Paragraph(
                    money_filter(
                        sum(sum_price_by_tax_rate.values())
                        - sum(sum_tax_by_tax_rate.values()),
                        currency,
                    ),
                    tstyle_bold_right,
                ),
                Paragraph(
                    money_filter(sum(sum_tax_by_tax_rate.values()), currency),
                    tstyle_bold_right,
                ),
                Paragraph(
                    money_filter(sum(sum_price_by_tax_rate.values()), currency),
                    tstyle_bold_right,
                ),
            ]
        )
        tstyledata += [
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
            ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (0, -1), 0),
            ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
        ]
        colwidths = [
            a * (self.pagesize[0] - 20 * mm)
            for a in [0.28, 0.1, 0.1, 0.1, 0.14, 0.14, 0.14]
        ]
        table = Table(tdata, colWidths=colwidths, repeatRows=1)
        table.setStyle(TableStyle(tstyledata))
        return [table]

    def _table_payments(self, form_data, currency):
        tstyle = copy.copy(self.get_style())
        tstyle.fontSize = 8
        tstyle.leading = 10
        tstyle_right = copy.copy(tstyle)
        tstyle_right.alignment = TA_RIGHT
        tstyle_bold = copy.copy(tstyle)
        tstyle_bold.fontName = "OpenSansBd"
        tstyle_bold_right = copy.copy(tstyle_bold)
        tstyle_bold_right.alignment = TA_RIGHT

        tdata = [
            [
                Paragraph(_("Payment method"), tstyle_bold),
                Paragraph(_("Payments"), tstyle_bold_right),
                Paragraph(_("Refunds"), tstyle_bold_right),
                Paragraph(_("Total"), tstyle_bold_right),
            ]
        ]

        p_qs = (
            self._payment_qs(form_data, currency)
            .order_by(
                "provider",
            )
            .values(
                "provider",
            )
            .annotate(
                sum_amount=Sum("amount"),
            )
        )
        r_qs = (
            self._refund_qs(form_data, currency)
            .order_by(
                "provider",
            )
            .values(
                "provider",
            )
            .annotate(
                sum_amount=Sum("amount"),
            )
        )

        tstyledata = []
        provider_names = dict(get_all_payment_providers())

        payments_by_provider = {r["provider"]: r["sum_amount"] for r in p_qs}
        refunds_by_provider = {r["provider"]: r["sum_amount"] for r in r_qs}

        providers = sorted(
            list(set(payments_by_provider.keys()) | set(refunds_by_provider.keys()))
        )
        for p in providers:
            tdata.append(
                [
                    Paragraph(provider_names.get(p, p), tstyle),
                    Paragraph(
                        money_filter(payments_by_provider[p], currency)
                        if p in payments_by_provider
                        else "",
                        tstyle_right,
                    ),
                    Paragraph(
                        money_filter(refunds_by_provider[p], currency)
                        if p in refunds_by_provider
                        else "",
                        tstyle_right,
                    ),
                    Paragraph(
                        money_filter(
                            payments_by_provider.get(p, Decimal("0.00"))
                            - refunds_by_provider.get(p, Decimal("0.00")),
                            currency,
                        ),
                        tstyle_right,
                    ),
                ]
            )

        tdata.append(
            [
                Paragraph(_("Sum"), tstyle_bold),
                Paragraph(
                    money_filter(
                        sum(payments_by_provider.values(), Decimal("0.00")), currency
                    ),
                    tstyle_bold_right,
                ),
                Paragraph(
                    money_filter(
                        sum(refunds_by_provider.values(), Decimal("0.00")), currency
                    ),
                    tstyle_bold_right,
                ),
                Paragraph(
                    money_filter(
                        sum(payments_by_provider.values(), Decimal("0.00"))
                        - sum(refunds_by_provider.values(), Decimal("0.00")),
                        currency,
                    ),
                    tstyle_bold_right,
                ),
            ]
        )
        tstyledata += [
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
            ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (0, -1), 0),
            ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
        ]
        colwidths = [a * (self.pagesize[0] - 20 * mm) for a in [0.58, 0.14, 0.14, 0.14]]
        table = Table(tdata, colWidths=colwidths, repeatRows=1)
        table.setStyle(TableStyle(tstyledata))
        return [table]

    def _table_open_items(self, form_data, currency):
        tstyle = copy.copy(self.get_style())
        tstyle.fontSize = 8
        tstyle.leading = 10
        tstyle_right = copy.copy(tstyle)
        tstyle_right.alignment = TA_RIGHT
        tstyle_center = copy.copy(tstyle)
        tstyle_center.alignment = TA_CENTER
        tstyle_bold = copy.copy(tstyle)
        tstyle_bold.fontName = "OpenSansBd"
        tstyle_bold_right = copy.copy(tstyle_bold)
        tstyle_bold_right.alignment = TA_RIGHT

        if form_data.get("date_range"):
            (
                df_start,
                df_end,
            ) = resolve_timeframe_to_datetime_start_inclusive_end_exclusive(
                now(), form_data["date_range"], self.timezone
            )
        else:
            df_start = df_end = None

        tstyledata = []
        tdata = []

        if df_start:
            tx_before = self._transaction_qs(form_data, currency, ignore_dates=True).filter(
                datetime__lt=df_start
            ).aggregate(s=Sum(F("count") * F("price")))["s"] or Decimal("0.00")
            p_before = self._payment_qs(form_data, currency, ignore_dates=True).filter(
                payment_date__lt=df_start
            ).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
            r_before = self._refund_qs(form_data, currency, ignore_dates=True).filter(
                execution_date__lt=df_start
            ).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
            open_before = tx_before - p_before + r_before
            tdata.append(
                [
                    Paragraph(
                        _("Pending payments at {datetime}").format(
                            datetime=date_format(
                                df_start - datetime.timedelta.resolution,
                                "SHORT_DATETIME_FORMAT",
                            )
                        ),
                        tstyle,
                    ),
                    "",
                    Paragraph(money_filter(open_before, currency), tstyle_right),
                ]
            )
        else:
            open_before = Decimal("0.00")

        tx_during = self._transaction_qs(form_data, currency).aggregate(
            s=Sum(F("count") * F("price"))
        )["s"] or Decimal("0.00")
        p_during = self._payment_qs(form_data, currency).aggregate(s=Sum("amount"))[
            "s"
        ] or Decimal("0.00")
        r_during = self._refund_qs(form_data, currency).aggregate(s=Sum("amount"))[
            "s"
        ] or Decimal("0.00")
        tdata.append(
            [
                Paragraph(_("Orders"), tstyle),
                Paragraph("+", tstyle_center),
                Paragraph(money_filter(tx_during, currency), tstyle_right),
            ]
        )
        tdata.append(
            [
                Paragraph(_("Payments"), tstyle),
                Paragraph("-", tstyle_center),
                Paragraph(money_filter(p_during, currency), tstyle_right),
            ]
        )
        tdata.append(
            [
                Paragraph(_("Refunds"), tstyle),
                Paragraph("+", tstyle_center),
                Paragraph(money_filter(r_during, currency), tstyle_right),
            ]
        )

        open_after = open_before + tx_during - p_during + r_during
        tdata.append(
            [
                Paragraph(
                    _("Pending payments at {datetime}").format(
                        datetime=date_format(
                            (df_end or now()) - datetime.timedelta.resolution,
                            "SHORT_DATETIME_FORMAT",
                        )
                    ),
                    tstyle_bold,
                ),
                Paragraph("=", tstyle_center),
                Paragraph(money_filter(open_after, currency), tstyle_bold_right),
            ]
        )
        tstyledata += [
            ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (0, -1), 0),
            ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
        ]
        colwidths = [a * (self.pagesize[0] - 20 * mm) for a in [0.8, 0.06, 0.14]]
        table = Table(tdata, colWidths=colwidths)
        table.setStyle(TableStyle(tstyledata))
        return [table]

    def _table_gift_cards(self, form_data, currency):
        tstyle = copy.copy(self.get_style())
        tstyle.fontSize = 8
        tstyle.leading = 10
        tstyle_right = copy.copy(tstyle)
        tstyle_right.alignment = TA_RIGHT
        tstyle_bold = copy.copy(tstyle)
        tstyle_bold.fontName = "OpenSansBd"
        tstyle_bold_right = copy.copy(tstyle_bold)
        tstyle_bold_right.alignment = TA_RIGHT

        if form_data.get("date_range"):
            df_start, df_end = resolve_timeframe_to_datetime_start_inclusive_end_exclusive(
                now(), form_data["date_range"], self.timezone
            )
        else:
            df_start = df_end = None

        tstyledata = []
        tdata = []

        if df_start:
            tx_before = self._giftcard_transaction_qs(
                form_data, currency, ignore_dates=True
            ).filter(datetime__lt=df_start).aggregate(s=Sum("value"))["s"] or Decimal(
                "0.00"
            )
            tdata.append(
                [
                    Paragraph(
                        _("Total gift card value at {datetime}").format(
                            datetime=date_format(
                                df_start - datetime.timedelta.resolution,
                                "SHORT_DATETIME_FORMAT",
                            )
                        ),
                        tstyle,
                    ),
                    Paragraph(money_filter(tx_before, currency), tstyle_right),
                ]
            )
        else:
            tx_before = Decimal("0.00")

        tx_during = self._giftcard_transaction_qs(form_data, currency).aggregate(s=Sum("value"))[
            "s"
        ] or Decimal("0.00")
        tdata.append(
            [
                Paragraph(_("Gift card transactions"), tstyle),
                Paragraph(money_filter(tx_during, currency), tstyle_right),
            ]
        )

        open_after = tx_before + tx_during
        tdata.append(
            [
                Paragraph(
                    _("Total gift card value at {datetime}").format(
                        datetime=date_format(
                            (df_end or now()) - datetime.timedelta.resolution,
                            "SHORT_DATETIME_FORMAT",
                        )
                    ),
                    tstyle_bold,
                ),
                Paragraph(money_filter(open_after, currency), tstyle_bold_right),
            ]
        )
        tstyledata += [
            ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (0, -1), 0),
            ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
        ]
        colwidths = [a * (self.pagesize[0] - 20 * mm) for a in [0.86, 0.14]]
        table = Table(tdata, colWidths=colwidths)
        table.setStyle(TableStyle(tstyledata))
        return [table]

    def _render_pdf(self, form_data, output_file=None):
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            ReportlabExportMixin.register_fonts()
            doc = self.get_doc_template()(
                output_file or f.name,
                pagesize=self.pagesize,
                leftMargin=10 * mm,
                rightMargin=10 * mm,
                topMargin=20 * mm,
                bottomMargin=15 * mm,
            )
            doc.addPageTemplates(
                [
                    PageTemplate(
                        id="All",
                        frames=self.get_frames(doc),
                        onPage=self.on_page,
                        pagesize=self.pagesize,
                    )
                ]
            )

            style_h1 = copy.copy(self.get_style())
            style_h1.fontName = "OpenSansBd"
            style_h1.fontSize = 14
            style_h2 = copy.copy(self.get_style())
            style_h2.fontName = "OpenSansBd"
            style_h2.fontSize = 12
            style_small = copy.copy(self.get_style())
            style_small.fontSize = 8
            style_small.leading = 10

            story = [
                Paragraph(self.verbose_name, style_h1),
                Spacer(0, 3 * mm),
                Paragraph(
                    "<br />".join(escape(f) for f in self.describe_filters(form_data)),
                    style_small,
                ),
            ]

            currencies = list(sorted(set(self.events.values_list('currency', flat=True).distinct())))

            for c in currencies:
                c_head = f" [{c}]" if len(currencies) > 1 else ""
                story += [
                    Spacer(0, 3 * mm),
                    Paragraph(_("Orders") + c_head, style_h2),
                    Spacer(0, 3 * mm),
                    *self._table_transactions(form_data, c),
                ]

            for c in currencies:
                c_head = f" [{c}]" if len(currencies) > 1 else ""
                story += [
                    Spacer(0, 8 * mm),
                    Paragraph(_("Payments") + c_head, style_h2),
                    Spacer(0, 3 * mm),
                    *self._table_payments(form_data, c),
                ]

            for c in currencies:
                c_head = f" [{c}]" if len(currencies) > 1 else ""
                story += [
                    Spacer(0, 8 * mm),
                    KeepTogether(
                        [
                            Paragraph(_("Open items") + c_head, style_h2),
                            Spacer(0, 3 * mm),
                            *self._table_open_items(form_data, c),
                        ]
                    ),
                ]
            if (
                self.is_multievent
                and self.events.count() == self.organizer.events.count()
            ):
                for c in currencies:
                    c_head = f" [{c}]" if len(currencies) > 1 else ""
                    story += [
                        Spacer(0, 8 * mm),
                        KeepTogether(
                            [
                                Paragraph(_("Gift cards") + c_head, style_h2),
                                Spacer(0, 3 * mm),
                                *self._table_gift_cards(form_data, c),
                            ]
                        ),
                    ]

            doc.build(story, canvasmaker=self.canvas_class(doc))
            f.seek(0)
            return (
                f"{self.get_filename()}.pdf",
                "application/pdf",
                None if output_file else f.read(),
            )

    def get_filename(self):
        if self.is_multievent:
            return f"{self.filename}-{self.organizer.slug}"
        else:
            return f"{self.filename}-{self.event.slug}"

    def render(self, form_data: dict, output_file=None):
        return self._render_pdf(form_data, output_file=output_file)
