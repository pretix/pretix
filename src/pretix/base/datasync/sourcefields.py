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

from collections import namedtuple
from functools import partial

from django.db.models import Max, Q
from django.utils.translation import gettext_lazy as _, pgettext_lazy

from pretix.base.models import Checkin, InvoiceAddress, Order, Question
from pretix.base.settings import PERSON_NAME_SCHEMES
from pretix.multidomain.urlreverse import build_absolute_uri


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


def normalize_email(email):
    if email:
        local, host = email.split("@")
        host = host.encode("idna").decode()
        return f"{local}@{host}"
    else:
        return None


def get_email_domain(email):
    if email:
        local, host = email.split("@")
        return host
    else:
        return None


ORDER_POSITION = 'position'
ORDER = 'order'
EVENT = 'event'
EVENT_OR_SUBEVENT = 'event_or_subevent'
AVAILABLE_MODELS = {
    'OrderPosition': (ORDER_POSITION, ORDER, EVENT_OR_SUBEVENT, EVENT),
    'Order': (ORDER, EVENT),
}

DataFieldCategory = namedtuple(
    'DataFieldCategory',
    field_names=('sort_index', 'label',),
)

CAT_ORDER_POSITION = DataFieldCategory(10, _('Order position details'))
CAT_ATTENDEE = DataFieldCategory(11, _('Attendee details'))
CAT_QUESTIONS = DataFieldCategory(12, _('Questions'))
CAT_PRODUCT = DataFieldCategory(20, _('Product details'))
CAT_ORDER = DataFieldCategory(21, _('Order details'))
CAT_INVOICE_ADDRESS = DataFieldCategory(22, _('Invoice address'))
CAT_EVENT = DataFieldCategory(30, _('Event information'))
CAT_EVENT_OR_SUBEVENT = DataFieldCategory(31, pgettext_lazy('subevent', 'Event or date information'))

DataFieldInfo = namedtuple(
    'DataFieldInfo',
    field_names=('required_input', 'category', 'key', 'label', 'type', 'enum_opts', 'getter', 'deprecated'),
    defaults=[False]
)


def get_invoice_address_or_empty(order):
    try:
        return order.invoice_address
    except InvoiceAddress.DoesNotExist:
        return InvoiceAddress()


def get_data_fields(event, for_model=None):
    """
    Returns tuple of (required_input, key, label, type, enum_opts, getter)

    Type is one of the Question types as defined in Question.TYPE_CHOICES.

    The data type of the return value of `getter` depends on `type`:
    - TYPE_CHOICE_MULTIPLE: list of strings
    - TYPE_CHOICE: list, containing zero or one strings
    - TYPE_BOOLEAN: boolean
    - all other (including TYPE_NUMBER): string
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
                CAT_ATTENDEE,
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
                CAT_ATTENDEE,
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
                CAT_ATTENDEE,
                "attendee_email",
                _("Attendee email"),
                Question.TYPE_STRING,
                None,
                lambda position: normalize_email(
                    position.attendee_email
                    or (position.addon_to.attendee_email if position.addon_to else None)
                ),
            ),
            DataFieldInfo(
                ORDER_POSITION,
                CAT_ATTENDEE,
                "attendee_or_order_email",
                _("Attendee or order email"),
                Question.TYPE_STRING,
                None,
                lambda position: normalize_email(
                    position.attendee_email
                    or (position.addon_to.attendee_email if position.addon_to else None)
                    or position.order.email
                ),
            ),
            DataFieldInfo(
                ORDER_POSITION,
                CAT_ATTENDEE,
                "attendee_company",
                _("Attendee company"),
                Question.TYPE_STRING,
                None,
                lambda position: position.company or (position.addon_to.company if position.addon_to else None),
            ),
            DataFieldInfo(
                ORDER_POSITION,
                CAT_ATTENDEE,
                "attendee_street",
                _("Attendee address street"),
                Question.TYPE_STRING,
                None,
                lambda position: position.street or (position.addon_to.street if position.addon_to else None),
            ),
            DataFieldInfo(
                ORDER_POSITION,
                CAT_ATTENDEE,
                "attendee_zipcode",
                _("Attendee address ZIP code"),
                Question.TYPE_STRING,
                None,
                lambda position: position.zipcode or (position.addon_to.zipcode if position.addon_to else None),
            ),
            DataFieldInfo(
                ORDER_POSITION,
                CAT_ATTENDEE,
                "attendee_city",
                _("Attendee address city"),
                Question.TYPE_STRING,
                None,
                lambda position: position.city or (position.addon_to.city if position.addon_to else None),
            ),
            DataFieldInfo(
                ORDER_POSITION,
                CAT_ATTENDEE,
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
                CAT_INVOICE_ADDRESS,
                "invoice_address_company",
                _("Invoice address company"),
                Question.TYPE_STRING,
                None,
                lambda order: get_invoice_address_or_empty(order).company,
            ),
            DataFieldInfo(
                ORDER,
                CAT_INVOICE_ADDRESS,
                "invoice_address_name",
                _("Invoice address name"),
                Question.TYPE_STRING,
                None,
                lambda order: get_invoice_address_or_empty(order).name,
            ),
        ]
        + [
            DataFieldInfo(
                ORDER,
                CAT_INVOICE_ADDRESS,
                "invoice_address_name_" + k,
                _("Invoice address") + ": " + label,
                Question.TYPE_STRING,
                None,
                partial(
                    lambda k, order: (get_invoice_address_or_empty(order).name_parts or {}).get(
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
                CAT_INVOICE_ADDRESS,
                "invoice_address_street",
                _("Invoice address street"),
                Question.TYPE_STRING,
                None,
                lambda order: get_invoice_address_or_empty(order).street,
            ),
            DataFieldInfo(
                ORDER,
                CAT_INVOICE_ADDRESS,
                "invoice_address_zipcode",
                _("Invoice address ZIP code"),
                Question.TYPE_STRING,
                None,
                lambda order: get_invoice_address_or_empty(order).zipcode,
            ),
            DataFieldInfo(
                ORDER,
                CAT_INVOICE_ADDRESS,
                "invoice_address_city",
                _("Invoice address city"),
                Question.TYPE_STRING,
                None,
                lambda order: get_invoice_address_or_empty(order).city,
            ),
            DataFieldInfo(
                ORDER,
                CAT_INVOICE_ADDRESS,
                "invoice_address_country",
                _("Invoice address country"),
                Question.TYPE_COUNTRYCODE,
                None,
                lambda order: str(get_invoice_address_or_empty(order).country),
            ),
            DataFieldInfo(
                ORDER,
                CAT_ORDER,
                "email",
                _("Order email"),
                Question.TYPE_STRING,
                None,
                lambda order: normalize_email(order.email),
            ),
            DataFieldInfo(
                ORDER,
                CAT_ORDER,
                "email_domain",
                _("Order email domain"),
                Question.TYPE_STRING,
                None,
                lambda order: get_email_domain(normalize_email(order.email)),
            ),
            DataFieldInfo(
                ORDER,
                CAT_ORDER,
                "order_code",
                _("Order code"),
                Question.TYPE_STRING,
                None,
                lambda order: order.code,
            ),
            DataFieldInfo(
                ORDER,
                CAT_ORDER,
                "event_order_code",
                _("Event and order code"),
                Question.TYPE_STRING,
                None,
                lambda order: order.full_code,
            ),
            DataFieldInfo(
                ORDER,
                CAT_ORDER,
                "order_total",
                _("Order total"),
                Question.TYPE_NUMBER,
                None,
                lambda order: str(order.total),
            ),
            DataFieldInfo(
                ORDER_POSITION,
                CAT_PRODUCT,
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
                CAT_PRODUCT,
                "product_id",
                _("Product ID"),
                Question.TYPE_NUMBER,
                None,
                lambda position: str(position.item.pk),
            ),
            DataFieldInfo(
                ORDER_POSITION,
                CAT_PRODUCT,
                "product_is_admission",
                _("Product is admission product"),
                Question.TYPE_BOOLEAN,
                None,
                lambda position: bool(position.item.admission),
            ),
            DataFieldInfo(
                EVENT,
                CAT_EVENT,
                "event_slug",
                _("Event short form"),
                Question.TYPE_STRING,
                None,
                lambda event: str(event.slug),
            ),
            DataFieldInfo(
                EVENT,
                CAT_EVENT,
                "event_name",
                _("Event name"),
                Question.TYPE_STRING,
                None,
                lambda event: str(event.name),
            ),
            DataFieldInfo(
                EVENT_OR_SUBEVENT,
                CAT_EVENT_OR_SUBEVENT,
                "event_date_from",
                _("Event start date"),
                Question.TYPE_DATETIME,
                None,
                lambda event_or_subevent: isoformat_or_none(event_or_subevent.date_from),
            ),
            DataFieldInfo(
                EVENT_OR_SUBEVENT,
                CAT_EVENT_OR_SUBEVENT,
                "event_date_to",
                _("Event end date"),
                Question.TYPE_DATETIME,
                None,
                lambda event_or_subevent: isoformat_or_none(event_or_subevent.date_to),
            ),
            DataFieldInfo(
                ORDER_POSITION,
                CAT_ORDER_POSITION,
                "voucher_code",
                _("Voucher code"),
                Question.TYPE_STRING,
                None,
                lambda position: position.voucher.code if position.voucher_id else "",
            ),
            DataFieldInfo(
                ORDER_POSITION,
                CAT_ORDER_POSITION,
                "ticket_id",
                _("Order code and position number"),
                Question.TYPE_STRING,
                None,
                lambda position: position.code,
            ),
            DataFieldInfo(
                ORDER_POSITION,
                CAT_ORDER_POSITION,
                "ticket_price",
                _("Ticket price"),
                Question.TYPE_NUMBER,
                None,
                lambda position: str(position.price),
            ),
            DataFieldInfo(
                ORDER,
                CAT_ORDER,
                "order_status",
                _("Order status"),
                Question.TYPE_CHOICE,
                Order.STATUS_CHOICE,
                lambda order: [order.status],
            ),
            DataFieldInfo(
                ORDER_POSITION,
                CAT_ORDER_POSITION,
                "ticket_status",
                _("Ticket status"),
                Question.TYPE_CHOICE,
                Order.STATUS_CHOICE,
                lambda position: [Order.STATUS_CANCELED if position.canceled else position.order.status],
            ),
            DataFieldInfo(
                ORDER,
                CAT_ORDER,
                "order_date",
                _("Order date and time"),
                Question.TYPE_DATETIME,
                None,
                lambda order: order.datetime.isoformat(),
            ),
            DataFieldInfo(
                ORDER,
                CAT_ORDER,
                "payment_date",
                _("Payment date and time"),
                Question.TYPE_DATETIME,
                None,
                get_payment_date,
            ),
            DataFieldInfo(
                ORDER,
                CAT_ORDER,
                "order_locale",
                _("Order locale"),
                Question.TYPE_CHOICE,
                [(lc, lc) for lc in event.settings.locales],
                lambda order: [order.locale],
            ),
            DataFieldInfo(
                ORDER_POSITION,
                CAT_ORDER_POSITION,
                "position_id",
                _("Order position ID"),
                Question.TYPE_NUMBER,
                None,
                lambda op: str(op.pk),
            ),
            DataFieldInfo(
                ORDER,
                CAT_ORDER,
                "presale_order_url",
                _("Order link"),
                Question.TYPE_STRING,
                None,
                lambda order: build_absolute_uri(
                    event,
                    'presale:event.order', kwargs={
                        'order': order.code,
                        'secret': order.secret,
                    }
                ),
            ),
            DataFieldInfo(
                ORDER_POSITION,
                CAT_ORDER_POSITION,
                "presale_ticket_url",
                _("Ticket link"),
                Question.TYPE_STRING,
                None,
                lambda op: build_absolute_uri(
                    event,
                    'presale:event.order.position', kwargs={
                        'order': op.order.code,
                        'secret': op.web_secret,
                        'position': op.positionid
                    }
                ),
            ),
        ]
        + [
            DataFieldInfo(
                ORDER_POSITION,
                CAT_ORDER_POSITION,
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
                CAT_QUESTIONS,
                "question_" + q.identifier,
                _("Question: {name}").format(name=str(q.question)),
                q.type,
                get_enum_opts(q),
                partial(lambda qq, position: get_answer(position, qq.identifier), q),
            )
            for q in event.questions.filter(~Q(type=Question.TYPE_FILE)).prefetch_related("options")
        ]
    )
    if not any(field_name == "given_name" for field_name, label, weight in name_scheme["fields"]):
        src_fields += [
            DataFieldInfo(
                ORDER_POSITION,
                CAT_ATTENDEE,
                "attendee_name_given_name",
                _("Attendee") + ": " + _("Given name") + " (⚠️ auto-generated, not recommended)",
                Question.TYPE_STRING,
                None,
                lambda position: split_name_on_last_space(position.attendee_name, part=0),
                deprecated=True,
            ),
            DataFieldInfo(
                ORDER,
                CAT_INVOICE_ADDRESS,
                "invoice_address_name_given_name",
                _("Invoice address") + ": " + _("Given name") + " (⚠️ auto-generated, not recommended)",
                Question.TYPE_STRING,
                None,
                lambda order: split_name_on_last_space(get_invoice_address_or_empty(order).name, part=0),
                deprecated=True,
            ),
        ]

    if not any(field_name == "family_name" for field_name, label, weight in name_scheme["fields"]):
        src_fields += [
            DataFieldInfo(
                ORDER_POSITION,
                CAT_ATTENDEE,
                "attendee_name_family_name",
                _("Attendee") + ": " + _("Family name") + " (⚠️ auto-generated, not recommended)",
                Question.TYPE_STRING,
                None,
                lambda position: split_name_on_last_space(position.attendee_name, part=1),
                deprecated=True,
            ),
            DataFieldInfo(
                ORDER,
                CAT_INVOICE_ADDRESS,
                "invoice_address_name_family_name",
                _("Invoice address") + ": " + _("Family name") + " (⚠️ auto-generated, not recommended)",
                Question.TYPE_STRING,
                None,
                lambda order: split_name_on_last_space(get_invoice_address_or_empty(order).name, part=1),
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


def get_enum_opts(q):
    if q.type in (Question.TYPE_CHOICE, Question.TYPE_CHOICE_MULTIPLE):
        return [(opt.identifier, opt.answer) for opt in q.options.all()]
    else:
        return None
