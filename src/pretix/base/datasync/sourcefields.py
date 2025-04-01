#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2025 rami.io GmbH and contributors
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

import json
from collections import namedtuple
from functools import partial

from django.db.models import Max
from django.utils.translation import gettext_lazy as _

from pretix.base.models import Checkin, Order, Question
from pretix.base.settings import PERSON_NAME_SCHEMES


def get_answer(op, question_identifier=None):
    a = None
    if op.addon_to:
        if "answers" in getattr(op.addon_to, "_prefetched_objects_cache", {}):
            try:
                a = [
                    a
                    for a in op.addon_to.answers.all()
                    if a.question.identifier == question_identifier
                ][0]
            except IndexError:
                pass
        else:
            a = op.addon_to.answers.filter(
                question__identifier=question_identifier
            ).first()

    if "answers" in getattr(op, "_prefetched_objects_cache", {}):
        try:
            a = [
                a
                for a in op.answers.all()
                if a.question.identifier == question_identifier
            ][0]
        except IndexError:
            pass
    else:
        a = op.answers.filter(question__identifier=question_identifier).first()

    if not a:
        return ""
    else:
        if a.question.type in (Question.TYPE_CHOICE, Question.TYPE_CHOICE_MULTIPLE):
            return [str(o.identifier) for o in a.options.all()]
        if a.question.type == Question.TYPE_BOOLEAN:
            return a.answer == "True"
        return a.answer


def get_payment_date(order):
    if order.status == Order.STATUS_PENDING:
        return None

    return isoformat_or_none(order.payments.aggregate(m=Max("payment_date"))["m"])


def isoformat_or_none(dt):
    return dt and dt.isoformat()


def first_checkin_on_list(list_pk, position):
    checkin = position.checkins.filter(
        list__pk=list_pk, type=Checkin.TYPE_ENTRY
    ).first()
    if checkin:
        return isoformat_or_none(checkin.datetime)


def split_name_on_last_space(name, part):
    name_parts = name.rsplit(" ", 1)
    return name_parts[part] if len(name_parts) > part else ""


ORDER_POSITION = 'position'
ORDER = 'order'
EVENT = 'event'
EVENT_OR_SUBEVENT = 'event_or_subevent'
AVAILABLE_MODELS = {
    'OrderPosition': (ORDER_POSITION, ORDER, EVENT_OR_SUBEVENT, EVENT),
    'Order': (ORDER, EVENT),
}


DataFieldInfo = namedtuple(
    'DataFieldInfo',
    field_names=('required_input', 'key', 'label', 'type', 'enum_opts', 'getter', 'deprecated'),
    defaults=[False]
)


def get_data_fields(event, for_model=None):
    """
    Returns tuple of (required_input, key, label, type, enum_opts, getter)

    type is one of the hubspot data types as specified in
    https://developers.hubspot.com/docs/api/crm/properties#property-type-and-fieldtype-values
    """
    name_scheme = PERSON_NAME_SCHEMES[event.settings.name_scheme]
    name_headers = []
    if name_scheme and len(name_scheme["fields"]) > 1:
        for k, label, w in name_scheme["fields"]:
            name_headers.append(label)

    src_fields = (
        [
            DataFieldInfo(
                ORDER_POSITION,
                "attendee_name",
                _("Attendee name"),
                Question.TYPE_STRING,
                None,
                lambda position: position.attendee_name
                or (position.addon_to.attendee_name if position.addon_to else None),
            ),
        ]
        + [
            DataFieldInfo(
                ORDER_POSITION,
                "attendee_name_" + k,
                _("Attendee") + ": " + label,
                Question.TYPE_STRING,
                None,
                partial(
                    lambda k, position: (
                        position.attendee_name_parts
                        or (position.addon_to.attendee_name_parts if position.addon_to else {})
                        or {}
                    ).get(k, ""),
                    k,
                ),
                deprecated=len(name_scheme["fields"]) == 1,
            )
            for k, label, w in name_scheme["fields"]
        ]
        + [
            DataFieldInfo(
                ORDER_POSITION,
                "attendee_email",
                _("Attendee email"),
                Question.TYPE_STRING,
                None,
                lambda position: position.attendee_email
                or (position.addon_to.attendee_email if position.addon_to else None),
            ),
            DataFieldInfo(
                ORDER_POSITION,
                "attendee_or_order_email",
                _("Attendee or order email"),
                Question.TYPE_STRING,
                None,
                lambda position: position.attendee_email
                or (position.addon_to.attendee_email if position.addon_to else None)
                or position.order.email,
            ),
            DataFieldInfo(
                ORDER_POSITION,
                "attendee_company",
                _("Attendee company"),
                Question.TYPE_STRING,
                None,
                lambda position: position.company or (position.addon_to.company if position.addon_to else None),
            ),
            DataFieldInfo(
                ORDER_POSITION,
                "attendee_street",
                _("Attendee address street"),
                Question.TYPE_STRING,
                None,
                lambda position: position.street or (position.addon_to.street if position.addon_to else None),
            ),
            DataFieldInfo(
                ORDER_POSITION,
                "attendee_zipcode",
                _("Attendee address ZIP code"),
                Question.TYPE_STRING,
                None,
                lambda position: position.zipcode or (position.addon_to.zipcode if position.addon_to else None),
            ),
            DataFieldInfo(
                ORDER_POSITION,
                "attendee_city",
                _("Attendee address city"),
                Question.TYPE_STRING,
                None,
                lambda position: position.city or (position.addon_to.city if position.addon_to else None),
            ),
            DataFieldInfo(
                ORDER_POSITION,
                "attendee_country",
                _("Attendee address country"),
                Question.TYPE_COUNTRYCODE,
                None,
                lambda position: str(
                    position.country or (position.addon_to.attendee_name if position.addon_to else "")
                ),
            ),
            DataFieldInfo(
                ORDER,
                "invoice_address_company",
                _("Invoice address company"),
                Question.TYPE_STRING,
                None,
                lambda order: order.invoice_address.company,
            ),
            DataFieldInfo(
                ORDER,
                "invoice_address_name",
                _("Invoice address name"),
                Question.TYPE_STRING,
                None,
                lambda order: order.invoice_address.name,
            ),
        ]
        + [
            DataFieldInfo(
                ORDER,
                "invoice_address_name_" + k,
                _("Invoice address") + ": " + label,
                Question.TYPE_STRING,
                None,
                partial(
                    lambda k, order: (order.invoice_address.name_parts or {}).get(
                        k, ""
                    ),
                    k,
                ),
                deprecated=len(name_scheme["fields"]) == 1,
            )
            for k, label, w in name_scheme["fields"]
        ]
        + [
            DataFieldInfo(
                ORDER,
                "invoice_address_street",
                _("Invoice address street"),
                Question.TYPE_STRING,
                None,
                lambda order: order.invoice_address.street,
            ),
            DataFieldInfo(
                ORDER,
                "invoice_address_zipcode",
                _("Invoice address ZIP code"),
                Question.TYPE_STRING,
                None,
                lambda order: order.invoice_address.zipcode,
            ),
            DataFieldInfo(
                ORDER,
                "invoice_address_city",
                _("Invoice address city"),
                Question.TYPE_STRING,
                None,
                lambda order: order.invoice_address.city,
            ),
            DataFieldInfo(
                ORDER,
                "invoice_address_country",
                _("Invoice address country"),
                Question.TYPE_COUNTRYCODE,
                None,
                lambda order: str(order.invoice_address.country),
            ),
            DataFieldInfo(
                ORDER,
                "email",
                _("Order email"),
                Question.TYPE_STRING,
                None,
                lambda order: order.email,
            ),
            DataFieldInfo(
                ORDER,
                "order_code",
                _("Order code"),
                Question.TYPE_STRING,
                None,
                lambda order: order.code,
            ),
            DataFieldInfo(
                ORDER,
                "event_order_code",
                _("Event and order code"),
                Question.TYPE_STRING,
                None,
                lambda order: order.full_code,
            ),
            DataFieldInfo(
                ORDER,
                "order_total",
                _("Order total"),
                Question.TYPE_NUMBER,
                None,
                lambda order: str(order.total),
            ),
            DataFieldInfo(
                ORDER_POSITION,
                "product",
                _("Product and variation name"),
                Question.TYPE_STRING,
                None,
                lambda position: str(
                    str(position.item.internal_name or position.item.name)
                    + ((" – " + str(position.variation.value)) if position.variation else "")
                ),
            ),
            DataFieldInfo(
                ORDER_POSITION,
                "product_id",
                _("Product ID"),
                Question.TYPE_NUMBER,
                None,
                lambda position: position.item.pk,
            ),
            DataFieldInfo(
                EVENT,
                "event_slug",
                _("Event short form"),
                Question.TYPE_STRING,
                None,
                lambda event: str(event.slug),
            ),
            DataFieldInfo(
                EVENT,
                "event_name",
                _("Event name"),
                Question.TYPE_STRING,
                None,
                lambda event: str(event.name),
            ),
            DataFieldInfo(
                EVENT_OR_SUBEVENT,
                "event_date_from",
                _("Event start date"),
                Question.TYPE_DATETIME,
                None,
                lambda event_or_subevent: isoformat_or_none(event_or_subevent.date_from),
            ),
            DataFieldInfo(
                EVENT_OR_SUBEVENT,
                "event_date_to",
                _("Event end date"),
                Question.TYPE_DATETIME,
                None,
                lambda event_or_subevent: isoformat_or_none(event_or_subevent.date_to),
            ),
            DataFieldInfo(
                ORDER_POSITION,
                "voucher_code",
                _("Voucher code"),
                Question.TYPE_STRING,
                None,
                lambda position: position.voucher.code if position.voucher_id else "",
            ),
            DataFieldInfo(
                ORDER_POSITION,
                "ticket_id",
                _("Ticket ID"),
                Question.TYPE_STRING,
                None,
                lambda position: position.code,
            ),
            DataFieldInfo(
                ORDER_POSITION,
                "ticket_price",
                _("Ticket price"),
                Question.TYPE_NUMBER,
                None,
                lambda position: str(position.price),
            ),
            DataFieldInfo(
                ORDER,
                "order_status",
                _("Order status"),
                Question.TYPE_CHOICE,
                Order.STATUS_CHOICE,
                lambda order: [str(order.status)],
            ),
            DataFieldInfo(
                ORDER,
                "order_date",
                _("Order date and time"),
                Question.TYPE_DATETIME,
                None,
                lambda order: order.datetime.isoformat(),
            ),
            DataFieldInfo(
                ORDER,
                "payment_date",
                _("Payment date and time"),
                Question.TYPE_DATETIME,
                None,
                get_payment_date,
            ),
            DataFieldInfo(
                ORDER,
                "order_locale",
                _("Order locale country code"),
                Question.TYPE_COUNTRYCODE,
                None,
                lambda order: order.locale.split("_")[0],
            ),
        ]
        + [
            DataFieldInfo(
                ORDER_POSITION,
                "checkin_date_" + str(cl.pk),
                _("Check-in datetime on list {}").format(cl.name),
                Question.TYPE_DATETIME,
                None,
                partial(first_checkin_on_list, cl.pk),
            )
            for cl in event.checkin_lists.all()
        ]
        + [
            DataFieldInfo(
                ORDER_POSITION,
                "question_" + q.identifier,
                _("Question: {name}").format(name=str(q.question)),
                q.type,
                get_enum_opts(q),
                partial(lambda qq, position: get_answer(position, qq.identifier), q),
            )
            for q in event.questions.all().prefetch_related("options")
        ]
    )
    if not any(field_name == "given_name" for field_name, label, weight in name_scheme["fields"]):
        src_fields += [
            DataFieldInfo(
                ORDER_POSITION,
                "attendee_name_given_name",
                _("Attendee") + ": " + _("Given name") + " (⚠️ auto-generated, not recommended)",
                Question.TYPE_STRING,
                None,
                lambda position: split_name_on_last_space(position.attendee_name, part=0),
                deprecated=True,
            ),
            DataFieldInfo(
                ORDER,
                "invoice_address_name_given_name",
                _("Invoice address") + ": " + _("Given name") + " (⚠️ auto-generated, not recommended)",
                Question.TYPE_STRING,
                None,
                lambda order: split_name_on_last_space(order.invoice_address.name, part=0),
                deprecated=True,
            ),
        ]

    if not any(field_name == "family_name" for field_name, label, weight in name_scheme["fields"]):
        src_fields += [
            DataFieldInfo(
                ORDER_POSITION,
                "attendee_name_family_name",
                _("Attendee") + ": " + _("Family name") + " (⚠️ auto-generated, not recommended)",
                Question.TYPE_STRING,
                None,
                lambda position: split_name_on_last_space(position.attendee_name.rsplit, part=1),
                deprecated=True,
            ),
            DataFieldInfo(
                ORDER,
                "invoice_address_name_family_name",
                _("Invoice address") + ": " + _("Family name") + " (⚠️ auto-generated, not recommended)",
                Question.TYPE_STRING,
                None,
                lambda order: split_name_on_last_space(order.invoice_address.name, part=1),
                deprecated=True,
            ),
        ]

    if for_model:
        available_inputs = AVAILABLE_MODELS[for_model]
        return [
            f for f in src_fields if f.required_input in available_inputs
        ]
    else:
        return src_fields


def translate_property_mappings(property_mapping, checkin_list_map):
    mappings = json.loads(property_mapping)

    for mapping in mappings:
        if mapping["pretix_field"].startswith("checkin_date_"):
            old_id = int(mapping["pretix_field"][len("checkin_date_"):])
            mapping["pretix_field"] = "checkin_date_%d" % checkin_list_map[old_id].pk
    return json.dumps(mappings)


def get_enum_opts(q):
    if q.type in (Question.TYPE_CHOICE, Question.TYPE_CHOICE_MULTIPLE):
        return [(opt.identifier, opt.answer) for opt in q.options.all()]
    else:
        return None


QUESTION_TYPE_IDENTIFIERS = {
    Question.TYPE_NUMBER: "NUMBER",
    Question.TYPE_STRING: "STRING",
    Question.TYPE_TEXT: "TEXT",
    Question.TYPE_BOOLEAN: "BOOLEAN",
    Question.TYPE_CHOICE: "CHOICE",
    Question.TYPE_CHOICE_MULTIPLE: "CHOICE_MULTIPLE",
    Question.TYPE_FILE: "FILE",
    Question.TYPE_DATE: "DATE",
    Question.TYPE_TIME: "TIME",
    Question.TYPE_DATETIME: "DATETIME",
    Question.TYPE_COUNTRYCODE: "COUNTRYCODE",
    Question.TYPE_PHONENUMBER: "PHONENUMBER",
}
